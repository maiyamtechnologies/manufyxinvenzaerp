"""
Retired. This patch used to backfill Payment Request.custom_payment_entry_created.

That customization (and the rest of the Payment Request customizations) moved to the
Payment Approval doctype -- see patches/v16/migrate_payment_request_to_payment_approval.py.
The patch name stays in patches.txt so sites that already ran it do not re-run it, and
fresh sites record it without doing anything.
"""


def execute():
    return
