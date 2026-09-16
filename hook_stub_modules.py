"""PyInstaller runtime hook: stub out heavy modules that pymobiledevice3
imports at top-level but our GUI never actually uses.

pymobiledevice3 hard-imports these in core modules:
  - pygments (service_connection.py, remotexpc.py): from pygments import formatters, highlight, lexers
  - traitlets (utils.py): from traitlets.config import Config
  - IPython (utils.py): import IPython
  - jedi, parso (transitive via IPython)

Our GUI code path never calls the functions that use these, so we replace
them with smart stubs that accept any attribute access / call without crashing.

prompt_toolkit is deliberately NOT stubbed: since pymobiledevice3 11.x,
utils.py hard-imports questionary, and questionary *subclasses* prompt_toolkit
classes at import time (``class InquirerControl(FormattedTextControl)``).  A
module stub cannot be used as a base class, so the only workable option is to
ship the real prompt_toolkit -- it is pure Python and costs ~1.5 MB.  See
fakegps.spec, which collects it via collect_submodules().

Submodules of the remaining roots resolve through _StubFinder, so the path list
does not have to be maintained by hand.  Hand-maintaining it is what broke the
v6.2.3 macOS build: questionary reached ``prompt_toolkit.validation``, that path
was missing from the list, and because ``pymobiledevice3.lockdown`` pulls in
utils.py, every device connection and location call raised ModuleNotFoundError
-- only device *listing* worked.
"""
import importlib
import importlib.machinery
import sys
import types


class _StubLoader:
    """Materialise any module under a stubbed root as a stub."""

    def create_module(self, spec):
        return _StubModule(spec.name)

    def exec_module(self, module):
        pass


class _StubModule(types.ModuleType):
    """A module stub that auto-creates attributes on access.

    - Attribute access returns another _StubModule (for submodule chains)
    - Calling it returns a _StubModule (for function stubs)
    - Supports 'from X import Y' because __getattr__ handles missing attrs
    """

    def __init__(self, name):
        super().__init__(name)
        self.__path__ = []
        self.__package__ = name.rpartition('.')[0] or name
        self.__loader__ = _StubLoader()
        self.__spec__ = importlib.machinery.ModuleSpec(
            name, self.__loader__, is_package=True)

    def __getattr__(self, name):
        # Don't recurse on dunder attrs used by import machinery
        if name.startswith('__') and name.endswith('__'):
            raise AttributeError(name)
        # Return a new stub for any attribute
        child_name = f"{self.__name__}.{name}"
        stub = _StubModule(child_name)
        # Cache it so repeated access returns the same object
        object.__setattr__(self, name, stub)
        # Also register in sys.modules so 'from X.Y import Z' works
        sys.modules.setdefault(child_name, stub)
        return stub

    def __call__(self, *args, **kwargs):
        """If the module is called like a function, return a stub."""
        return _StubModule(f"{self.__name__}.result")

    def __bool__(self):
        return True

    def __iter__(self):
        return iter([])

    def __repr__(self):
        return f"<StubModule '{self.__name__}'>"


class _StubFinder:
    """Resolve any submodule of a stubbed root to a stub.

    Sits at the front of sys.meta_path, so the entire subtree is stubbed
    without a hand-maintained path list.
    """

    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] not in STUB_ROOTS:
            return None
        return importlib.machinery.ModuleSpec(
            fullname, _StubLoader(), is_package=True)


def _stub_highlight(*args, **kwargs):
    """Stub for pygments.highlight() — returns input text unchanged."""
    if args:
        return str(args[0])
    return ""


# ── Register stubs for all heavy excluded modules ──

STUB_ROOTS = [
    'IPython',
    'jedi',
    'parso',
    'pygments',
    'traitlets',
]

sys.meta_path.insert(0, _StubFinder())

for name in STUB_ROOTS:
    if name not in sys.modules:
        sys.modules[name] = _StubModule(name)

# ── Specific functional stubs ──

# pygments.highlight is called as a function
pygments_mod = sys.modules['pygments']
object.__setattr__(pygments_mod, 'highlight', _stub_highlight)

# traitlets.config.Config is instantiated
traitlets_config = importlib.import_module('traitlets.config')


class _StubConfig:
    """Stub for traitlets.config.Config — accepts any kwargs."""
    def __init__(self, *args, **kwargs):
        self._data = kwargs

    def __getattr__(self, name):
        if name.startswith('_'):
            raise AttributeError(name)
        return _StubConfig()

    def __setattr__(self, name, value):
        if name.startswith('_'):
            object.__setattr__(self, name, value)
        else:
            self.__dict__.setdefault('_data', {})[name] = value

    def merge(self, other):
        return self

    def copy(self):
        return _StubConfig(**self._data)


object.__setattr__(traitlets_config, 'Config', _StubConfig)

# IPython.start_ipython is called in utils.py
ipython_mod = sys.modules['IPython']
object.__setattr__(ipython_mod, 'start_ipython',
                   lambda *a, **kw: None)
