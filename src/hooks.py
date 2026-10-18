"""Extension contracts: third-party adapters are trusted Python modules.

A bank adapter must implement sync(ledger) and return stats.
An accounting sink must implement name and post(approved_tx)->external_reference.
"""
import importlib


def load_adapter(spec):
    """Opt-in plugin loader. Example: my_company.accounting:ERPAdapter.

    Do not load unreviewed modules: importing a module runs its Python code.
    """
    if ':' not in spec:
        raise ValueError("Adapter must be package.module:Class")
    module, class_name=spec.split(':',1)
    if not module or not class_name or module.startswith('.'):
        raise ValueError("Invalid adapter module")
    return getattr(importlib.import_module(module),class_name)()
