"""CRM API client.

Importable shortcut::

    from piquano_core.crm_client import CRMClient
"""
from .client import CRMClient, CRMClientError

__all__ = ["CRMClient", "CRMClientError"]
