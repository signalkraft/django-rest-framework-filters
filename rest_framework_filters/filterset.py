from __future__ import absolute_import
from __future__ import unicode_literals

from copy import copy

try:
    from django.db.models.constants import LOOKUP_SEP
except ImportError:  # pragma: nocover
    # Django < 1.5 fallback
    from django.db.models.sql.constants import LOOKUP_SEP  # noqa
from django.db import models
from django.utils.datastructures import SortedDict
from django.db.models.related import RelatedObject
from django.utils import six

import django_filters
import django_filters.filters
import django_filters.filterset
from django_filters.filterset import get_model_field

from . import filters


class FilterSetMeta(django_filters.filterset.FilterSetMetaclass):
    def __new__(cls, name, bases, attrs):
        new_cls = super(FilterSetMeta, cls).__new__(cls, name, bases, attrs)

        for name, filter_ in six.iteritems(new_cls.base_filters):
            if isinstance(filter_, filters.RelatedFilter):
                # Populate our FilterSet fields with the fields we've stored
                # in RelatedFilter.
                filter_.setup_filterset()
                new_cls.populate_from_filterset(filter_.filterset, filter_, name, new_cls.base_filters)
                # Add an 'isnull' filter to allow checking if the relation is empty.
                isnull_filter = filters.BooleanFilter(name=("%s%sisnull" % (filter_.name, LOOKUP_SEP)))
                new_cls.base_filters['%s%s%s' % (filter_.name, LOOKUP_SEP, 'isnull')] = isnull_filter
            elif isinstance(filter_, filters.AllLookupsFilter):
                # Populate our FilterSet fields with all the possible
                # filters for the AllLookupsFilter field.
                model = new_cls._meta.model
                field = get_model_field(model, filter_.name)
                if not field:
                    continue
                for lookup_type in new_cls.LOOKUP_TYPES:
                    if isinstance(field, RelatedObject):
                        f = new_cls.filter_for_reverse_field(field, filter_.name)
                    else:
                        f = new_cls.filter_for_field(field, filter_.name)
                    f.lookup_type = lookup_type
                    f = new_cls.fix_filter_field(f)
                    new_cls.base_filters["%s%s%s" % (name, LOOKUP_SEP, lookup_type)] = f
        return new_cls


class FilterSet(six.with_metaclass(FilterSetMeta, django_filters.FilterSet)):
    # In order to support ISO-8601 -- which is the default output for
    # DRF -- we need to set up custom date/time input formats.
    filter_overrides = {
        models.DateTimeField: {
            'filter_class': filters.DateTimeFilter,
        }, 
        models.DateField: {
            'filter_class': filters.DateFilter,
        }, 
        models.TimeField: {
            'filter_class': filters.TimeFilter,
        },
    }

    LOOKUP_TYPES = django_filters.filters.LOOKUP_TYPES

    @classmethod
    def fix_filter_field(cls, f):
        """
        Fix the filter field based on the lookup type. 
        """
        lookup_type = f.lookup_type
        if lookup_type == 'isnull':
            return filters.BooleanFilter(name=("%s%sisnull" % (f.name, LOOKUP_SEP)))
        return f

    @classmethod
    def populate_from_filterset(cls, filterset, filter_, name, filters_):
        """
        Populate `filters` with filters provided on `filterset`.
        """
        def _should_skip():
            for name, filter_ in six.iteritems(filters_):
                # Already there, so skip it.
                if ('%s%s%s' % (name, LOOKUP_SEP, f.name)) in filters_:
                    return True
                if isinstance(filter_, filters.RelatedFilter) and isinstance(f, filters.RelatedFilter):
                    # Avoid infinite recursion on recursive relations.
                    if isinstance(cls, filterset):
                        return True
                if f == filter_:
                    return True
            return False

        for f in filterset.base_filters.values():
            if _should_skip():
                continue
    
            f = copy(f)

            # Guess on the field to join on, if applicable
            if not getattr(f, 'parent_relation', None):
                f.parent_relation = filterset._meta.model.__name__.lower()

            # We use filter_.name -- which is the internal name, to do the actual query
            filter_name = f.name 
            f.name = '%s%s%s' % (filter_.name, LOOKUP_SEP, filter_name)
            # and then we use the /given/ name keyword as the actual querystring lookup.
            filters_['%s%s%s' % (name, LOOKUP_SEP, filter_name)] = f
