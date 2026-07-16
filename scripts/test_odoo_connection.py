"""Standalone sanity check for Odoo XML-RPC credentials, before wiring them into the app.

Usage:
    python scripts/test_odoo_connection.py <odoo_url> <db> <username> <password>

Example:
    python scripts/test_odoo_connection.py http://localhost:8069 odoo admin admin
"""

import sys
import xmlrpc.client


def main() -> None:
    if len(sys.argv) != 5:
        print(__doc__)
        sys.exit(1)

    url, db, username, password = sys.argv[1:5]

    common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common")
    print("Odoo server version:", common.version())

    uid = common.authenticate(db, username, password, {})
    if not uid:
        print("Authentication FAILED - check ODOO_DB / ODOO_USERNAME / ODOO_PASSWORD")
        sys.exit(1)
    print(f"Authenticated OK, uid={uid}")

    models = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object")

    employees = models.execute_kw(
        db, uid, password, "hr.employee", "search_read", [[]], {"fields": ["id", "name", "barcode"], "limit": 20}
    )
    print("\nFound employees (showing up to 20 of possibly more):")
    for emp in employees:
        print(f"  id={emp['id']:>5}  barcode={emp['barcode'] or '(none)':<12}  name={emp['name']}")
    print(
        "\n-> employee_id sent to POST /register and returned by /verify must match the 'barcode' "
        "above (not 'id') - set a Barcode on the employee in Odoo if it's empty."
    )

    can_write = models.execute_kw(
        db, uid, password, "hr.attendance", "check_access_rights", ["write"], {"raise_exception": False}
    )
    print(f"\nCan write hr.attendance: {can_write}")
    if not can_write:
        print(
            "  <-- This user cannot write hr.attendance for other employees. Grant it an "
            "Attendance 'Administrator' (or Officer) role in Odoo Settings > Users, not just "
            "'Employee' self-service, otherwise /verify will fail with an access error."
        )


if __name__ == "__main__":
    main()
