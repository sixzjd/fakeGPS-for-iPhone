"""PyInstaller runtime hook: stub out heavy modules that pymobiledevice3
imports at top-level but our GUI never actually uses.

pymobiledevice3 hard-imports these in core modules:
  - pygments (service_connection.py, remotexpc.py): from pygments import formatters, highlight, lexers
  - traitlets (utils.py): from traitlets.config import Config
  - IPython (utils.py): import IPython
  - prompt_toolkit (cli/ only, but transitive)
  - jedi, parso (transitive via IPython)

Our GUI code path never calls the functions that use these, so we replace
them with smart stubs that accept any attribute access / call without crashing.
"""
import sys
import types


class _StubModule(types.ModuleType):
    """A module stub that auto-creates attributes on access.

    - Attribute access returns another _StubModule (for submodule chains)
    - Calling it returns a _StubModule (for function stubs)
    - Supports 'from X import Y' because __getattr__ handles missing attrs
    """

    def __init__(self, name, package=None):
        super().__init__(name)
        self.__path__ = []
        self.__package__ = package or name
        self.__loader__ = None
        self.__spec__ = None

    def __getattr__(self, name):
        # Don't recurse on dunder attrs used by import machinery
        if name.startswith('__') and name.endswith('__'):
            raise AttributeError(name)
        # Return a new stub for any attribute
        child_name = f"{self.__name__}.{name}"
        stub = _StubModule(child_name, package=self.__name__)
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
    'prompt_toolkit',
    'pygments',
    'traitlets',
]

# Pre-register known deep submodule paths so 'from X.Y.Z import W' works
DEEP_PATHS = [
    # pygments (used by service_connection.py, remotexpc.py)
    'pygments.formatters',
    'pygments.lexers',
    'pygments.styles',
    'pygments.token',
    # traitlets (used by utils.py)
    'traitlets.config',
    'traitlets.config.loader',
    # IPython (used by utils.py)
    'IPython.core',
    'IPython.core.getipython',
    'IPython.core.application',
    'IPython.core.crashhandler',
    'IPython.core.ultratb',
    'IPython.core.interactiveshell',
    'IPython.terminal',
    'IPython.terminal.embed',
    'IPython.terminal.interactiveshell',
    # jedi
    'jedi.api',
    # prompt_toolkit (CLI only, but might be transitively imported)
    'prompt_toolkit.application',
    'prompt_toolkit.auto_suggest',
    'prompt_toolkit.completion',
    'prompt_toolkit.completion.base',
    'prompt_toolkit.document',
    'prompt_toolkit.history',
    'prompt_toolkit.styles',
]

# Register all stubs
for name in STUB_ROOTS + DEEP_PATHS:
    if name not in sys.modules:
        sys.modules[name] = _StubModule(name)

# Link parent → child attributes
# e.g. sys.modules['pygments'].formatters should be sys.modules['pygments.formatters']
for name in DEEP_PATHS:
    parts = name.split('.')
    for i in range(1, len(parts)):
        parent_name = '.'.join(parts[:i])
        child_name = '.'.join(parts[:i + 1])
        child_attr = parts[i]
        parent = sys.modules.get(parent_name)
        child = sys.modules.get(child_name)
        if parent and child:
            try:
                object.__setattr__(parent, child_attr, child)
            except (AttributeError, TypeError):
                pass

# ── Specific functional stubs ──

# pygments.highlight is called as a function
pygments_mod = sys.modules['pygments']
object.__setattr__(pygments_mod, 'highlight', _stub_highlight)

# traitlets.config.Config is instantiated
traitlets_config = sys.modules['traitlets.config']


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
