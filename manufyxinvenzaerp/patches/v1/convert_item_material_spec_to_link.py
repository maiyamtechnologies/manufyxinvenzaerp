"""Convert Item Material Spec from Data to Link once, before after_migrate.

The Material Spec DocType exists by post_model_sync. Frappe rejects a normal
Custom Field save for Data -> Link, even though both use the same text column.
The helper creates master records for any existing Item values before updating
the Custom Field metadata, so no existing specification is lost.
"""

from manufyxinvenzaerp.setup import prepare_material_spec_link


def execute():
    prepare_material_spec_link()
