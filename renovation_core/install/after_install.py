from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from renovation_core.renovation_core.doctype.renovation_docfield.renovation_docfield import add_all_reqd_table_fields
from renovation_core.renovation_core.doctype.renovation_sidebar.renovation_sidebar import make_sample_sidebar



def after_install():
  make_app_field_in_custom_field_and_property_setter()
  make_app_field_in_custom_field_and_property_setter()
  add_all_reqd_table_fields()
  make_sample_sidebar()


def make_app_field_in_custom_field_and_property_setter():
  create_custom_fields({
      "Custom Field": {
          "fieldname": "app_name",
          "label": "App Name",
          "fieldtype": "Data",
          "insert_after": "dt",
          "print_hide": 1,
          "options": ""
      },
      "Property Setter": {
          "fieldname": "app_name",
          "label": "App Name",
          "fieldtype": "Data",
          "insert_after": "doc_type",
          "print_hide": 1,
          "options": ""
      }
  })
