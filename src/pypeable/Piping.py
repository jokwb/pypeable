"""
Pipeable: operator-based function piping for Python.

Usage:
    from pipeable import PipeMeta, Pipe, EndPipe

    class MyObj(metaclass=PipeMeta):              # defaults to |
        ...

    class MyObj(metaclass=PipeMeta, operator=">>"):  # use >> instead
        ...

    result = (
        obj.method1().method2()
        | Pipe(func).path.to["key"].attr
        | Pipe("method_name", arg1, arg2).nested.obj
        | EndPipe.back_to_methods().and_more()
    )
"""


def _walk(obj, parts):
    for kind, key in parts:
        if kind == "attr":
            try:
                obj = getattr(obj, key)
            except AttributeError:
                obj = obj[key]
        else:
            obj = obj[key]
    return obj


def _set_at(obj, parts, value):
    *parents, (last_kind, last_key) = parts
    target = _walk(obj, parents)
    if last_kind == "attr":
        setattr(target, last_key, value)
    else:
        target[last_key] = value


class Pipe:
    """Wrap a callable for piping. Chain attribute/item access to target a path.

    Pipe(func)                          — whole-object transform
    Pipe(func, x, key=v)               — with extra args (obj always first)
    Pipe("method", arg)                 — call a method by name
    Pipe(func).graph.nodes["A"].weight  — target a nested attribute in-place
    """

    __slots__ = ("_fn", "_args", "_kwargs", "_path")

    def __init__(self, fn, *args, **kwargs):
        object.__setattr__(self, "_fn", fn)
        object.__setattr__(self, "_args", args)
        object.__setattr__(self, "_kwargs", kwargs)
        object.__setattr__(self, "_path", ())

    def _clone_with(self, step):
        clone = object.__new__(Pipe)
        object.__setattr__(clone, "_fn", self._fn)
        object.__setattr__(clone, "_args", self._args)
        object.__setattr__(clone, "_kwargs", self._kwargs)
        object.__setattr__(clone, "_path", (*self._path, step))
        return clone

    def __getattr__(self, name):
        return self._clone_with(("attr", name))

    def __getitem__(self, key):
        return self._clone_with(("item", key))

    def __call__(self, obj):
        if self._path:
            current = _walk(obj, self._path)
            if isinstance(self._fn, str):
                getattr(current, self._fn)(*self._args, **self._kwargs)
            else:
                result = self._fn(current, *self._args, **self._kwargs)
                if result is not None:
                    _set_at(obj, self._path, result)
            return obj
        if isinstance(self._fn, str):
            getattr(obj, self._fn)(*self._args, **self._kwargs)
            return obj
        result = self._fn(obj, *self._args, **self._kwargs)
        return obj if result is None else result

    def __repr__(self):
        name = getattr(self._fn, "__name__", str(self._fn))
        if self._path:
            segs = []
            for kind, key in self._path:
                segs.append(f".{key}" if kind == "attr" else f"[{key!r}]")
            return f"Pipe({name}){''.join(segs)}"
        return f"Pipe({name})"


class _ClosingProxy:
    """Records attribute access and calls, replays them when the pipe executes."""

    __slots__ = ("_deferred",)

    def __init__(self, deferred=()):
        object.__setattr__(self, "_deferred", deferred)

    def __getattr__(self, name):
        return _ClosingProxy((*self._deferred, ("getattr", name)))

    def __call__(self, *args, **kwargs):
        return _ClosingProxy((*self._deferred, ("call", args, kwargs)))

    def _execute(self, obj):
        current = obj
        for op in self._deferred:
            if op[0] == "getattr":
                current = getattr(current, op[1])
            elif op[0] == "call":
                current = current(*op[1], **op[2])
        return current


EndPipe = _ClosingProxy()


def _pipe_dispatch(self_value, other):
    """Shared dispatch logic for all pipe operators."""
    if isinstance(other, _ClosingProxy):
        return other._execute(self_value)
    if isinstance(other, Pipe) or callable(other):
        return Piped(other(self_value))
    return NotImplemented


class Piped:
    """Wrapper for intermediate results that keeps the chain alive."""

    def __init__(self, value):
        self._value = value

    @property
    def value(self):
        return self._value

    def __or__(self, other):
        return _pipe_dispatch(self._value, other)

    def __rshift__(self, other):
        return _pipe_dispatch(self._value, other)

    def __lshift__(self, other):
        return _pipe_dispatch(self._value, other)

    def __repr__(self):
        return repr(self._value)

    def __str__(self):
        return str(self._value)


class PipeMeta(type):
    """Metaclass that injects pipe support into any class.

    Usage:
        class MyObj(metaclass=PipeMeta):                # uses |
        class MyObj(metaclass=PipeMeta, operator=">>"):  # uses >>
        class MyObj(metaclass=PipeMeta, operator="<<"):  # uses <<
    """

    _OPERATORS = {
        "|": "__or__",
        ">>": "__rshift__",
        "<<": "__lshift__",
    }

    def __new__(mcs, name, bases, namespace, operator="|", **kwargs):
        cls = super().__new__(mcs, name, bases, namespace, **kwargs)
        dunder = mcs._OPERATORS.get(operator)
        if not dunder:
            raise ValueError(
                f"Unsupported operator {operator!r}. "
                f"Choose from: {', '.join(mcs._OPERATORS)}"
            )

        original = namespace.get(dunder)

        def pipe_op(self, other, _original=original):
            if isinstance(other, _ClosingProxy):
                return other._execute(self)
            if isinstance(other, Pipe) or callable(other):
                return Piped(other(self))
            if _original:
                return _original(self, other)
            return NotImplemented

        setattr(cls, dunder, pipe_op)
        return cls


# ── demo ──────────────────────────────────────────────────────────────

if __name__ == "__main__":

    class Node:
        def __init__(self, name, weight=1.0, tags=None):
            self.name = name
            self.weight = weight
            self.tags = tags or []

        def __repr__(self):
            return f"Node({self.name!r}, w={self.weight}, tags={self.tags})"

    class Graph:
        def __init__(self):
            self.nodes = {}

        def add(self, node):
            self.nodes[node.name] = node
            return self

    # ── test with | (default) ──

    class ProjectOr(metaclass=PipeMeta):
        def __init__(self, graph):
            self.graph = graph

        def report(self):
            print("  report:", self)
            return self

        def save(self, path="default.out"):
            print(f"  saved to {path}")
            return self

        def __repr__(self):
            nodes = ", ".join(f"{k}: {v}" for k, v in self.graph.nodes.items())
            return f"Project({nodes})"

    # ── test with >> ──

    class ProjectShift(metaclass=PipeMeta, operator=">>"):
        def __init__(self, graph):
            self.graph = graph

        def report(self):
            print("  report:", self)
            return self

        def save(self, path="default.out"):
            print(f"  saved to {path}")
            return self

        def __repr__(self):
            nodes = ", ".join(f"{k}: {v}" for k, v in self.graph.nodes.items())
            return f"Project({nodes})"

    def clamp(val, lo, hi):
        return max(lo, min(hi, val))

    def add_tag(tags, tag):
        return tags + [tag]

    # --- | operator ---
    print("=== using | ===")
    g1 = Graph()
    g1.add(Node("A", weight=3.0, tags=["input"]))
    g1.add(Node("B", weight=7.0, tags=["output"]))
    p1 = ProjectOr(g1)

    result1 = (
        p1
        | Pipe(lambda w: w / 10).graph.nodes["A"].weight
        | Pipe(clamp, 0.0, 1.0).graph.nodes["B"].weight
        | EndPipe.report().save("pipe.csv")
    )
    print(f"  type: {type(result1).__name__}\n")

    # --- >> operator ---
    print("=== using >> ===")
    g2 = Graph()
    g2.add(Node("A", weight=3.0, tags=["input"]))
    g2.add(Node("B", weight=7.0, tags=["output"]))
    p2 = ProjectShift(g2)

    result2 = (
        p2
        >> Pipe(lambda w: w / 10).graph.nodes["A"].weight
        >> Pipe(clamp, 0.0, 1.0).graph.nodes["B"].weight
        >> EndPipe.report().save("shift.csv")
    )
    print(f"  type: {type(result2).__name__}")
