from frappe.model.document import Document


class SalesOrderDeliveryPlan(Document):
    """One finished drawing on the Sales Order's Delivery Plan tab.

    Every figure except Delivery Plan (Nos) is derived and rewritten by
    selling_management.delivery_plan -- see refresh_delivery_plan.
    """

    pass
