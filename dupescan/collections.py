import collections.abc


class DelimitedStringDict(collections.abc.MutableMapping):
    __slots__ = ("_separator", "_root", "_len")

    class Node(object):
        __slots__ = ("prefix", "branches", "leaves")

        def __init__(self):
            self.branches = dict()
            self.leaves = dict()

    def __init__(self, separator, *initial_args, **initial_kwargs):
        self._separator = separator
        self._root = DelimitedStringDict.Node()
        self._len = 0

        if initial_args or initial_kwargs:
            self.update(*initial_args, **initial_kwargs)

    def _iter_nodes(self):
        q = [ ("", self._root) ]
        while len(q) > 0:
            prefix, node = q.pop()
            yield prefix, node
            prefix_sep = prefix + self._separator
            q.extend(
                (prefix_sep + name, child_node)
                for name, child_node in node.branches.items()
            )

    def _get_node_and_leaf(self, string, create):
        if not isinstance(string, str):
            raise TypeError("DelimitedStringDict keys must be of type str")
        branches = string.split(self._separator)
        leaf = branches.pop()
        node = self._root
        for b in branches:
            if b not in node.branches:
                if create:
                    node.branches[b] = DelimitedStringDict.Node()
                else:
                    return None, leaf
            node = node.branches[b]

        return node, leaf

    @property
    def separator(self):
        return self._separator

    def __len__(self):
        return self._len

    def __contains__(self, string):
        node, leaf = self._get_node_and_leaf(string, create=False)
        if node is None:
            return False
        return leaf in node.leaves

    def __getitem__(self, key):
        node, leaf = self._get_node_and_leaf(key, create=False)
        if node is None:
            raise KeyError(key)
        try:
            return node.leaves[leaf]
        except KeyError:
            raise KeyError(key)

    def __setitem__(self, key, value):
        node, leaf = self._get_node_and_leaf(key, create=True)
        if leaf not in node.leaves:
            self._len += 1
        node.leaves[leaf] = value

    def __delitem__(self, key):
        node, leaf = self._get_node_and_leaf(key, create=False)
        if node is None:
            raise KeyError(key)
        try:
            del node.leaves[leaf]
            self._len -= 1
        except KeyError:
            raise KeyError(key)

    def keys(self):
        for prefix, node in self._iter_nodes():
            for k in node.leaves.keys():
                yield prefix + k

    __iter__ = keys

    def values(self):
        for _, node in self._iter_nodes():
            for v in node.leaves.values():
                yield v

    def items(self):
        for prefix, node in self._iter_nodes():
            for k, v in node.leaves.items():
                yield prefix + k, v

    def __eq__(self, other):
        if not isinstance(other, collections.abc.MutableMapping):
            return NotImplemented
        if self._len != len(other):
            return False
        try:
            for key, value in self.items():
                if value != other[key]:
                    return False
        except KeyError:
            return False
        return True

    def clear(self):
        self._root = DelimitedStringDict.Node()
        self._len = 0


class DelimitedStringSet(collections.abc.MutableSet):
    __slots__ = ("_dsd",)

    def __init__(self, separator, initial_content=None):
        self._dsd = DelimitedStringDict(separator)
        if initial_content is not None:
            self |= initial_content

    def _from_iterable(self, iterable):
        # note that in the base class, this is defined as a @classmethod.  here
        # it's an instance method as __init__ needs a value for separator, and
        # providing self's makes the most sense. this should work as the base
        # class code only accessess this method from instances, rather than
        # classes, although that's not documented
        return DelimitedStringSet(self.separator, iterable)

    @property
    def separator(self):
        return self._dsd._separator

    def __len__(self):
        return self._dsd._len

    def __contains__(self, x):
        return x in self._dsd

    def __iter__(self):
        for k in self._dsd.keys():
            yield k

    def add(self, string):
        self._dsd[string] = 1

    def remove(self, value):
        del self._dsd[value]

    def discard(self, value):
        try:
            del self._dsd[value]
        except KeyError:
            pass

    def clear(self):
        self._dsd.clear()

    def copy(self):
        return self._from_iterable(self)
