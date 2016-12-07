"""Python Utilities. Functions in this module are not supposed to invoke the backend."""

import random
import string
from collections import OrderedDict

from ..legacy import pykit as py


def vectorize_function(_string_stamper=None):
    """
    Decorator for vectorizing a function with proper broadcasting. Exercise extreme caution when using with
    functions that take lists as inputs.
    """
    # TODO Write moar doc

    # Default string stamper
    if _string_stamper is None:
        _string_stamper = lambda s: s

    def _vectorize_function(function):

        def _function(*args, **kwargs):
            # The first task is to get the vector length.
            vector_length = max([py.smartlen(arg) for arg in list(args) + list(kwargs.values())])

            # Make sure the given lists are consistent (i.e. smartlen either 1 or vector_length)
            assert all([py.smartlen(arg) == 1 or py.smartlen(arg) == vector_length
                        for arg in list(args) + list(kwargs.values())]), _string_stamper("Cannot broadcast arguments "
                                                                                         "/ vectorize function.")

            # Broadcast arguments
            broadcasted_args = [arg if py.smartlen(arg) == vector_length else py.broadcast(arg, vector_length)
                                for arg in args]

            # Broadcast keyword arguments <unreadable python-fu>
            broadcasted_kwargs = [[{key: value} for value in
                                   (kwargs[key] if py.smartlen(kwargs[key]) == vector_length else
                                    py.obj2list(kwargs[key]) * vector_length)]
                                  for key in kwargs.keys()]
            # </unreadable python-fu>

            # Output list
            outputs = []
            for arg, kwarg in zip(zip(*broadcasted_args), zip(*broadcasted_kwargs)):
                # kwarg is now a list of dictionaries. Put all these dicts to another, bigger dict
                big_kw_dict = dict([item for kw_dict in kwarg for item in kw_dict.items()])
                outputs.append(function(*arg, **big_kw_dict))

            return outputs

        return _function

    return _vectorize_function


class DictList(OrderedDict):
    """
    This class brings some of the list goodies to OrderedDict (including number indexing), with the caveat that
    keys are only allowed to be strings.
    """

    def __init__(self, item_list, **kwds):
        # Try to make item_list compatible without looking for key conflicts
        item_list = self._make_compatible(item_list, find_key_conflicts=False)
        # Init superclass
        super(DictList, self).__init__(item_list, **kwds)
        # Raise exception if non-string found in keys
        if not all([isinstance(key, str) for key in self.keys()]):
            raise TypeError("Keys in a DictList must be string.")

    def __setitem__(self, key, value, dict_setitem=dict.__setitem__):
        # This method is overridden to intercept keys and check whether they're strings
        if not isinstance(key, str):
            raise TypeError("Keys in a DictList must be strings.")
        super(DictList, self).__setitem__(key, value, dict_setitem=dict_setitem)

    def __getitem__(self, item):
        # This is where things get interesting. This function is overridden to enable number indexing.
        if not isinstance(item, (str, int, slice)):
            raise TypeError("DictList indices must be slices, integers "
                            "or strings, not {}.".format(item.__class__.__name__))
        # Case one: item is a string
        if isinstance(item, str):
            # Fall back to the superclass' getitem
            return super(DictList, self).__getitem__(item)
        else:
            # item is an integer. Fetch from list and return
            return self.values()[item]

    def _is_compatible(self, obj, find_key_conflicts=True):
        """Checks if a given object is convertable to OrderedDict."""
        # Check types
        if isinstance(obj, (OrderedDict, DictList, dict)):
            code = 1
        elif isinstance(obj, list):
            code = 2 if all([py.smartlen(elem) == 2 for elem in obj]) else 3
        else:
            code = 0

        # Check for key conflicts
        if find_key_conflicts and (code == 1 or code == 2):
            if not set(self.keys()) - set(OrderedDict(obj).keys()):
                # Key conflict found, obj not compatible
                code = 0
        # Done.
        return code

    def _make_compatible(self, obj, find_key_conflicts=True):
        # Get compatibility code.
        code = self._is_compatible(obj, find_key_conflicts=find_key_conflicts)

        # Convert code 3
        if code == 3:
            compatible_obj = []
            for elem in obj:
                taken_keys = zip(*compatible_obj)[0] if compatible_obj else None
                generated_id = self._generate_id(taken_keys=taken_keys)
                compatible_obj.append((generated_id, elem))
            obj = compatible_obj
        elif code == 1 or code == 2:
            # Object is compatible already, nothing to do here.
            pass
        else:
            raise ValueError("Object could not be made compatible with DictList.")

        return obj

    def append(self, x):
        # This is custom behaviour.
        # This method 'appends' x to the dict, but without a given key.
        # This is done by setting str(id(x)) as the dict key.
        self.update({self._generate_id(taken_keys=self.keys()): x})

    def extend(self, t):
        # Try to make t is compatible
        t = self._make_compatible(t)
        # Convert t to list, and piggy back on the superclass' update method
        self.update(list(t))

    def __add__(self, other):
        # Enable list concatenation with +
        # Try to make other compatible
        self._make_compatible(other)
        # Use OrderedDict constructor
        return DictList(self.items() + list(other))

    @staticmethod
    def _generate_id(taken_keys=None):
        _SIZE = 10
        taken_keys = [] if taken_keys is None else taken_keys

        while True:
            generated_id = ''.join(random.SystemRandom().choice(string.ascii_lowercase + string.digits)
                                   for _ in range(_SIZE))
            # If generated_id is not taken, break and return, otherwise, retry.
            if generated_id not in taken_keys:
                return generated_id
            else:
                continue


class ParameterCollection(DictList):
    """Class to collect parameters of a layer."""
    def __init__(self, item_list, **kwds):
        # Initialize superclass
        super(ParameterCollection, self).__init__(item_list, **kwds)
        # Validate contents of the built
        self._validate_items()

    def __getitem__(self, item):
        # Check if item is a string to start with

        if isinstance(item, str):
            # So far so good. Now check whether it's a parameter tag
            if self._is_parameter_tag(item):
                return super(ParameterCollection, self).__getitem__(item)
            else:
                # FIXME This is about as inefficient as it gets. I know, a few seconds do not matter
                # FIXME if you're training a network, but there has to be a better way
                # FIXME (e.g. caching names and layer_id's).
                # Check if it's a parameter name.
                names_found = self.find(parameter_name=item)
                # Check if it's a layer id
                layers_found = self.find(layer_id=item)
                # Check if item is both a layerID and parameter name
                if bool(names_found) ^ bool(layers_found):
                    return py.delist(names_found) if names_found else py.delist(layers_found)
                else:
                    # item is both a layerID and parameter name
                    #
                    raise KeyError("Item(s) {} is(are) both LayerID(s) and parameter name(s). "
                                   "Resolve conflict by using parameter tags.".format(names_found))
        else:
            # Let the superclass handle this mess
            return super(ParameterCollection, self).__getitem__(item)

    def find(self, layer_id=None, parameter_name=None):
        # Enforce early stopping if both layer_id and parameter_name is given
        stop_when_found = layer_id is not None and parameter_name is not None
        # Instantiate a list to put search results in
        found = []
        # Search
        for item_key, item_value in self.items():
            current_layer_id, current_parameter_name = self._split_parameter_tag(item_key, check=True)
            # Check if there's a match
            layer_id_match = True if layer_id is None else layer_id == current_layer_id
            parameter_name_match = True if parameter_name is None else parameter_name == current_parameter_name
            # Append to found if there is a match, keep looking otherwise
            if layer_id_match and parameter_name_match:
                found.append(item_value)
                if stop_when_found:
                    break
            else:
                continue
        # Done
        return found

    def __setitem__(self, key, value):
        # Check if key is a parameter tag
        if not self._is_parameter_tag(key):
            raise ValueError("Key {} is not a parameter tag.".format(key))
        super(ParameterCollection, self).__setitem__(key, value)

    def set(self, layer_id, parameter_name, value):
        self.__setitem__(self._get_parameter_tag(layer_id, parameter_name), value)

    def as_list(self):
        return self.values()

    def _validate_items(self, items=None):
        # Use items in the dict if items is not given
        items = self.items() if items is None else items
        for item_key, item_value in items:
            if not self._is_parameter_tag(item_key):
                raise ValueError("Key {} is not a valid parameter tag.".format(item_key))

    _is_parameter_tag = is_parameter_tag
    _split_parameter_tag = split_parameter_tag
    _get_parameter_tag = get_parameter_tag


def is_parameter_tag(tag):
    """
    Check if a tag (str) is a parameter tag. Parameter tags look like e.g.: '[LayerID:conv1][W]' for a layer named
    'conv1' and parameter named 'W'.
    """
    return isinstance(tag, str) and tag.startswith("[LayerID:") and tag.endswith("]") and tag.find('][') != -1


def split_parameter_tag(tag, check=False):
    """
    Splits a parameter tag to LayerID and parameter name.
    Example:
        split_parameter_tag('[LayerID:conv1][W]') -> ('conv1', 'W')
    """
    if check:
        assert is_parameter_tag(tag), "The tag to be split '{}' is not a valid parameter tag.".format(tag)
    # First, strip the exterior square brackets
    layer_id_tag, parameter_name = tag.strip('[]').split('][')
    # Get layer ID from tag
    layer_id = layer_id_tag.replace('LayerID:', '')
    # Done
    return layer_id, parameter_name


def get_parameter_tag(layer_id, parameter_name):
    """Gets parameter tag given a layer_id and a parameter name."""
    return "[LayerID:{}][{}]".format(layer_id, parameter_name)