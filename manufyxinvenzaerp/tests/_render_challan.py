import frappe
from frappe.utils.pdf import get_pdf
from manufyxinvenzaerp.manufyxinvenzaerp.doctype.delivery_challan.delivery_challan import (
    _render_delivery_challan_html,
)

def run(name="GP-00059", out="/tmp/out.pdf"):
    doc = frappe.get_doc("Delivery Challan", name)
    html = _render_delivery_challan_html(doc)
    open(out, "wb").write(get_pdf(html))
    print("wrote", out, "for", name)
