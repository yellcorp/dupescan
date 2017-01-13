import operator


def compose_unary(outer_unary_func, inner_func):
    def composite_func(*args, **kwargs):
        return outer_unary_func(inner_func(*args, **kwargs))
    return composite_func


def not_of(func):
    return compose_unary(operator.not_, func)


def negative_of(func):
    return compose_unary(operator.neg, func)


def and_of(func_a, func_b):
    if func_a is None:
        return func_b

    if func_b is None:
        return func_a

    def composite_func(*args, **kwargs):
        return func_a(*args, **kwargs) and func_b(*args, **kwargs)
    return composite_func
