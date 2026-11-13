"""Create the Director role and the four people who approve payments.

Runs before doctype sync because Payment Approval's permissions name the role.

Each approver is created if missing (enabled, System User, Director role, no welcome
email -- live has no outgoing Email Account) or, if the user already exists, simply given
the Director role. No password is set here, and none belongs in the repo: set one from
the User form (Change Password / Set New Password) before they first log in."""

import frappe

DIRECTORS = {
    "thamizhdasan@manufyx.co.in": "Thamizhdasan",
    "sanjeeviraja@manufyx.co.in": "Sanjeeviraja",
    "mohanraj@manufyx.co.in": "Mohanraj",
    "sathish@manufyx.co.in": "Sathish",
}


def execute():
    if not frappe.db.exists("Role", "Director"):
        frappe.get_doc({"doctype": "Role", "role_name": "Director", "desk_access": 1}).insert(ignore_permissions=True)

    for email, first_name in DIRECTORS.items():
        if not frappe.db.exists("User", email):
            frappe.get_doc(
                {
                    "doctype": "User",
                    "email": email,
                    "first_name": first_name,
                    "enabled": 1,
                    "user_type": "System User",
                    "send_welcome_email": 0,
                    "roles": [{"role": "Director"}],
                }
            ).insert(ignore_permissions=True)
            continue

        user = frappe.get_doc("User", email)
        if "Director" not in [r.role for r in user.roles]:
            user.append("roles", {"role": "Director"})
            user.flags.ignore_validate = True
            user.save(ignore_permissions=True)
