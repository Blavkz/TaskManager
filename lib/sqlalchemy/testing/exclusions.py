# testing/exclusions.py
# Copyright (C) 2005-2023 the SQLAlchemy authors and contributors
# <see AUTHORS file>
#
# This module is part of SQLAlchemy and is released under
# the MIT License: https://www.opensource.org/licenses/mit-license.php


import contextlib
import operator
import re
import sys

from . import config
from .. import util
from ..util import decorator
from ..util.compat import inspect_getfullargspec


def skip_if(predicate, reason=None):
    rule = compound()
    pred = _as_predicate(predicate, reason)
    rule.skips.add(pred)
    return rule


def fails_if(predicate, reason=None):
    rule = compound()
    pred = _as_predicate(predicate, reason)
    rule.fails.add(pred)
    return rule


class compound(object):
    def __init__(self):
        self.fails = set()
        self.skips = set()
        self.tags = set()

    def __add__(self, other):
        return self.add(other)

    def as_skips(self):
        rule = compound()
        rule.skips.update(self.skips)
        rule.skips.update(self.fails)
        rule.tags.update(self.tags)
        return rule

    def add(self, *others):
        copy = compound()
        copy.fails.update(self.fails)
        copy.skips.update(self.skips)
        copy.tags.update(self.tags)
        for other in others:
            copy.fails.update(other.fails)
            copy.skips.update(other.skips)
            copy.tags.update(other.tags)
        return copy

    def not_(self):
        copy = compound()
        copy.fails.update(NotPredicate(fail) for fail in self.fails)
        copy.skips.update(NotPredicate(skip) for skip in self.skips)
        copy.tags.update(self.tags)
        return copy

    @property
    def enabled(self):
        return self.enabled_for_config(config._current)

    def enabled_for_config(self, config):
        for predicate in self.skips.union(self.fails):
            if predicate(config):
                return False
        else:
            return True

    def matching_config_reasons(self, config):
        return [
            predicate._as_string(config)
            for predicate in self.skips.union(self.fails)
            if predicate(config)
        ]

    def include_test(self, include_tags, exclude_tags):
        return bool(
            not self.tags.intersection(exclude_tags)
            and (not include_tags or self.tags.intersection(include_tags))
        )

    def _extend(self, other):
        self.skips.update(other.skips)
        self.fails.update(other.fails)
        self.tags.update(other.tags)

    def __call__(self, fn):
        if hasattr(fn, "_sa_exclusion_extend"):
            fn._sa_exclusion_extend._extend(self)
            return fn

        @decorator
        def decorate(fn, *args, **kw):
            return self._do(config._current, fn, *args, **kw)

        decorated = decorate(fn)
        decorated._sa_exclusion_extend = self
        return decorated

    @contextlib.contextmanager
    def fail_if(self):
        all_fails = compound()
        all_fails.fails.update(self.skips.union(self.fails))

        try:
            yield
        except Exception as ex:
            all_fails._expect_failure(config._current, ex)
        else:
            all_fails._expect_success(config._current)

    def _do(self, cfg, fn, *args, **kw):
        for skip in self.skips:
            if skip(cfg):
                msg = "'%s' : %s" % (
                    config.get_current_test_name(),
                    skip._as_string(cfg),
                )
                config.skip_test(msg)

        try:
            return_value = fn(*args, **kw)
        except Exception as ex:
            self._expect_failure(cfg, ex, name=fn.__name__)
        else:
            self._expect_success(cfg, name=fn.__name__)
            return return_value

    def _expect_failure(self, config, ex, name="block"):
        for fail in self.fails:
            if fail(config):
                if util.py2k:
                    str_ex = unicode(ex).encode(  # noqa: F821
                        "utf-8", errors="ignore"
                    )
                else:
                    str_ex = str(ex)
                print(
                    (
                        "%s failed as expected (%s): %s "
                        % (name, fail._as_string(config), str_ex)
                    )
                )
                break
        else:
            util.raise_(ex, with_traceback=sys.exc_info()[2])

    def _expect_success(self, config, name="block"):
        if not self.fails:
            return

        for fail in self.fails:
            if fail(config):
                raise AssertionError(
                    "Unexpected success for '%s' (%s)"
                    % (
                        name,
                        " and ".join(
                            fail._as_string(config) for fail in self.fails
                        ),
                    )
                )


def requires_tag(tagname):
    return tags([tagname])


def tags(tagnames):
    comp = compound()
    comp.tags.update(tagnames)
    return comp


def only_if(predicate, reason=None):
    predicate = _as_predicate(predicate)
    return skip_if(NotPredicate(predicate), reason)


def succeeds_if(predicate, reason=None):
    predicate = _as_predicate(predicate)
    return fails_if(NotPredicate(predicate), reason)


class Predicate(object):
    @classmethod
    def as_predicate(cls, predicate, description=None):
        if isinstance(predicate, compound):
            return cls.as_predicate(predicate.enabled_for_config, description)
        elif isinstance(predicate, Predicate):
            if description and predicate.description is None:
                predicate.description = description
            return predicate
        elif isinstance(predicate, (list, set)):
            return OrPredicate(
                [cls.as_predicate(pred) for pred in predicate], description
            )
        elif isinstance(predicate, tuple):
            return SpecPredicate(*predicate)
        elif isinstance(predicate, util.string_types):
            tokens = re.match(
                r"([\+\w]+)\s*(?:(>=|==|!=|<=|<|>)\s*([\d\.]+))?", predicate
            )
            if not tokens:
                raise ValueError(
                    "Couldn't locate DB name in predicate: %r" % predicate
                )
            db = tokens.group(1)
            op = tokens.group(2)
            spec = (
                tuple(int(d) for d in tokens.group(3).split("."))
                if tokens.group(3)
                else None
            )

            return SpecPredicate(db, op, spec, description=description)
        elif callable(predicate):
            return LambdaPredicate(predicate, description)
        else:
            assert False, "unknown predicate type: %s" % predicate

    def _format_description(self, config, negate=False):
        bool_ = self(config)
        if negate:
            bool_ = not negate
        return self.description % {
            "driver": config.db.url.get_driver_name()
            if config
            else "<no driver>",
            "database": config.db.url.get_backend_name()
            if config
            else "<no database>",
            "doesnt_support": "doesn't support" if bool_ else "does support",
            "does_support": "does support" if bool_ else "doesn't support",
        }

    def _as_string(self, config=None, negate=False):
        raise NotImplementedError()


class BooleanPredicate(Predicate):
    def __init__(self, value, description=None):
        self.value = value
        self.description = description or "boolean %s" % value

    def __call__(self, config):
        return self.value

    def _as_string(self, config, negate=False):
        return self._format_description(config, negate=negate)


class SpecPredicate(Predicate):
    def __init__(self, db, op=None, spec=None, description=None):
        self.db = db
        self.op = op
        self.spec = spec
        self.description = description

    _ops = {
        "<": operator.lt,
        ">": operator.gt,
        "==": operator.eq,
        "!=": operator.ne,
        "<=": operator.le,
        ">=": operator.ge,
        "in": operator.contains,
        "between": lambda val, pair: val >= pair[0] and val <= pair[1],
    }

    def __call__(self, config):
        if config is None:
            return False

        engine = config.db

        if "+" in self.db:
            dialect, driver = self.db.split("+")
        else:
            dialect, driver = self.db, None

        if dialect and engine.name != dialect:
            return False
        if driver is not None and engine.driver != driver:
            return False

        if self.op is not None:
            assert driver is None, "DBAPI version specs not supported yet"

            version = _server_version(engine)
            oper = (
                hasattr(self.op, "__call__") and self.op or self._ops[self.op]
            )
            return oper(version, self.spec)
        else:
            return True

    def _as_string(self, config, negate=False):
        if self.description is not None:
            return self._format_description(config)
        elif self.op is None:
            if negate:
                return "not %s" % self.db
            else:
                return "%s" % self.db
        else:
            if negate:
                return "not %s %s %s" % (self.db, self.op, self.spec)
            else:
                return "%s %s %s" % (self.db, self.op, self.spec)


class LambdaPredicate(Predicate):
    def __init__(self, lambda_, description=None, args=None, kw=None):
        spec = inspect_getfullargspec(lambda_)
        if not spec[0]:
            self.lambda_ = lambda db: lambda_()
        else:
            self.lambda_ = lambda_
        self.args = args or ()
        self.kw = kw or {}
        if description:
            self.description = description
        elif lambda_.__doc__:
            self.description = lambda_.__doc__
        else:
            self.description = "custom function"

    def __call__(self, config):
        return self.lambda_(config)

    def _as_string(self, config, negate=False):
        return self._format_description(config)


class NotPredicate(Predicate):
    def __init__(self, predicate, description=None):
        self.predicate = predicate
        self.description = description

    def __call__(self, config):
        return not self.predicate(config)

    def _as_string(self, config, negate=False):
        if self.description:
            return self._format_description(config, not negate)
        else:
            return self.predicate._as_string(config, not negate)


class OrPredicate(Predicate):
    def __init__(self, predicates, description=None):
        self.predicates = predicates
        self.description = description

    def __call__(self, config):
        for pred in self.predicates:
            if pred(config):
                return True
        return False

    def _eval_str(self, config, negate=False):
        if negate:
            conjunction = " and "
        else:
            conjunction = " or "
        return conjunction.join(
            p._as_string(config, negate=negate) for p in self.predicates
        )

    def _negation_str(self, config):
        if self.description is not None:
            return "Not " + self._format_description(config)
        else:
            return self._eval_str(config, negate=True)

    def _as_string(self, config, negate=False):
        if negate:
            return self._negation_str(config)
        else:
            if self.description is not None:
                return self._format_description(config)
            else:
                return self._eval_str(config)


_as_predicate = Predicate.as_predicate


def _is_excluded(db, op, spec):
    return SpecPredicate(db, op, spec)(config._current)


def _server_version(engine):
    """Return a server_version_info tuple."""

    # force metadata to be retrieved
    conn = engine.connect()
    version = getattr(engine.dialect, "server_version_info", None)
    if version is None:
        version = ()
    conn.close()
    return version


def db_spec(*dbs):
    return OrPredicate([Predicate.as_predicate(db) for db in dbs])


def open():  # noqa
    return skip_if(BooleanPredicate(False, "mark as execute"))


def closed():
    return skip_if(BooleanPredicate(True, "marked as skip"))


def fails(reason=None):
    return fails_if(BooleanPredicate(True, reason or "expected to fail"))


@decorator
def future(fn, *arg):
    return fails_if(LambdaPredicate(fn), "Future feature")


def fails_on(db, reason=None):
    return fails_if(db, reason)


def fails_on_everything_except(*dbs):
    return succeeds_if(OrPredicate([Predicate.as_predicate(db) for db in dbs]))


def skip(db, reason=None):
    return skip_if(db, reason)


def only_on(dbs, reason=None):
    return only_if(
        OrPredicate(
            [Predicate.as_predicate(db, reason) for db in util.to_list(dbs)]
        )
    )


def exclude(db, op, spec, reason=None):
    return skip_if(SpecPredicate(db, op, spec), reason)


def against(config, *queries):
    assert queries, "no queries sent!"
    return OrPredicate([Predicate.as_predicate(query) for query in queries])(
        config
    )
