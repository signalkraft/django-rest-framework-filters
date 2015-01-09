from copy import copy, deepcopy

try:
    from django.db.models.constants import LOOKUP_SEP
except ImportError:  # pragma: nocover
    # Django < 1.5 fallback
    from django.db.models.sql.constants import LOOKUP_SEP  # noqa
from django.utils.datastructures import SortedDict
from django.db.models.related import RelatedObject
from django.utils import six

import django_filters
from django_filters.filters import LOOKUP_TYPES
from django_filters.filterset import get_model_field

from .filters import RelatedFilter, AllLookupsFilter

def populate_from_filterset(cls, filterset, name, parent_filter, filters):
    """
    Populate `filters` with filters provided on `filterset`.
    """
    def _should_skip():
        for name, filter_ in six.iteritems(filters):
            # Already there, so skip it.
            if ('%s%s%s' % (name, LOOKUP_SEP, f.name)) in filters:
                return True
            if isinstance(filter_, RelatedFilter) and isinstance(f, RelatedFilter):
                # Avoid infinite recursion on recursive relations.
                if isinstance(cls, filterset):
                    return True
            if f == filter_:
                return True
        return False

    to_populate = deepcopy(filterset.base_filters.values())
    for f in to_populate:
        if _should_skip():
            continue
        
        f = copy(f)
        old_field_name = f.name
        f.name = '%s%s%s' % (parent_filter.name, LOOKUP_SEP, f.name)
        filters['%s%s%s' % (name, LOOKUP_SEP, old_field_name)] = f


class ChainedFilterSet(django_filters.FilterSet):
    def __new__(cls, *args, **kwargs):
        new_cls = super(ChainedFilterSet, cls).__new__(cls, *args, **kwargs)
        already_included = {}

        for name, filter_ in six.iteritems(new_cls.base_filters):
            if isinstance(filter_, RelatedFilter):
                # Populate our FilterSet fields with the fields we've stored
                # in RelatedFilter.
                #if not _should_include_filter(filter_):
                #    continue
                filter_.setup_filterset()
                populate_from_filterset(new_cls, filter_.filterset, name, filter_, new_cls.base_filters)
            elif isinstance(filter_, AllLookupsFilter):
                # Populate our FilterSet fields with all the possible
                # filters for the AllLookupsFilter field.
                model = new_cls._meta.model
                field = get_model_field(model, filter_.name)
                for lookup_type in LOOKUP_TYPES:
                    if isinstance(field, RelatedObject):
                        f = new_cls.filter_for_reverse_field(field, filter_.name)
                    else:
                        f = new_cls.filter_for_field(field, filter_.name)
                    f.lookup_type = lookup_type
                    new_cls.base_filters["%s__%s" % (name, lookup_type)] = f

        return new_cls
