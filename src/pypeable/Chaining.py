from dataclasses import dataclass, field
from sys import _getframe
from types import BuiltinFunctionType, FunctionType
from typing import Any, Callable

_ValueSentinel = object()


@dataclass
class _FnContainer:
    fn: Callable
    named_kwarg: str | object = _ValueSentinel
    args: tuple[Any, ...] = field(default_factory=tuple)
    kwargs: dict[str, Any] = field(default_factory=dict)


class C:
    def __init__(self, lazy: bool = False):
        self.fn = None
        self.lazy = lazy
        self.value = _ValueSentinel
        self.kwarg = _ValueSentinel
        self.lazy_fns: list[_FnContainer] = []

    def _forward(self, forward_value: Any) -> C:
        _c = C(lazy=self.lazy)
        _c.value = forward_value
        _c.lazy_fns = self.lazy_fns
        return _c

    def __getitem__(self, argname: str | object):
        if argname is _ValueSentinel:
            return self
        self.kwarg = argname
        return self

    def _execute(self, fn, value, named_kwarg, args, kwargs) -> Any:
        if named_kwarg is not _ValueSentinel:
            kwargs.update({named_kwarg: value})
            return fn(*args, **kwargs)
        elif value is not _ValueSentinel:
            return fn(value, *args, **kwargs)
        return fn(*args, **kwargs)

    def _store(self, args, kwargs):
        lazy_fn = _FnContainer(
            fn=self.fn,
            named_kwarg=self.kwarg,
            args=args,
            kwargs=kwargs,
        )
        self.lazy_fns.append(lazy_fn)

    def __call__(self, *args, **kwargs):
        if self.fn is None:
            raise RuntimeError(f"No registered function in {self}.")

        try:
            if not self.lazy:
                forward_value = self._execute(
                    self.fn, self.value, self.kwarg, args, kwargs
                )

            else:
                self._store(args, kwargs)
                forward_value = _ValueSentinel

            return self._forward(forward_value)

        except Exception as e:
            print(e)
            raise RuntimeError(
                f"Unable to dispatch new chain from {self} with function {self.fn.__name__} and value {self.value}."
            ) from e

    def __getattr__(self, k: str):
        element = _getframe(1).f_globals[k]
        if not isinstance(element, (FunctionType, BuiltinFunctionType)):
            raise TypeError(f"Error in {self}: {k} is not FunctionType.")

        self.fn = element
        return self

    def __repr__(self):
        return repr(self.value)

    def unwrap(self):
        if not self.lazy:
            return self.value

        value = _ValueSentinel
        for fnc in self.lazy_fns:
            fn = fnc.fn
            value = self._execute(fn, value, fnc.named_kwarg, fnc.args, fnc.kwargs)

        return value


if __name__ == "__main__":
    import re
    from math import sqrt

    def fn1(a: int, b: int) -> int:
        return a + b

    def fn2(a: int) -> str:
        return f"I'm a string now containing the number {a}!"

    def fn3(a: str) -> str:
        return re.findall(r"\d", a)[0]

    def fn4(a: int, second_argument: str):
        return f"{a} -- {second_argument}"

    def fn5(s: str, pos: int):
        return s[pos]

    def fn6(d: str) -> int:
        return int(d)

    result = (
        C(lazy=False)
        .fn1(2, 5)
        .fn2()
        .fn3()
        .fn4["second_argument"](4)
        .fn5(pos=-1)
        .fn6()
        .sqrt()
        .unwrap()
    )

    print(result)
