import re

import frappe
from frappe import throw, _, msgprint
from frappe.core.doctype.sms_settings.sms_settings import get_headers
from six import string_types
from frappe.defaults import get_user_default
from frappe.utils import now_datetime, nowtime, get_time
import ast


def validate_receiver_nos(receiver_list):
  plus = frappe.db.get_value('SMS Settings', None, 'start_with_plus')
  validated_receiver_list = []
  for d in receiver_list:
    # remove invalid character
    for x in [' ', '-', '(', ')']:
      d = d.replace(x, '')
    if plus and plus == "Add" and d[0] != '+':
      d = '+'+d
    elif plus and plus == "Remove" and d[0] == '+':
      d = d[1:]
    validated_receiver_list.append(d)

  if not validated_receiver_list:
    throw(_("Please enter valid mobile nos"))
  return validated_receiver_list


@frappe.whitelist()
def send_sms(receiver_list, msg, sender_name='', success_msg=True, provider=None):

  import json
  if isinstance(receiver_list, string_types):
    receiver_list = json.loads(receiver_list)
    if not isinstance(receiver_list, list):
      receiver_list = [receiver_list]

  receiver_list = validate_receiver_nos(receiver_list)

  arg = {
      'receiver_list': receiver_list,
      'message'		: frappe.safe_decode(msg).encode('utf-8'),
      'success_msg'	: success_msg
  }
  if provider or get_user_default("sms_settings"):
    return send_via_gateway(arg, provider=provider or get_user_default("sms_settings"))
  else:
    msgprint(_("Please set default SMS Settings form System Setting."))
    return "Fail"


def send_via_gateway(arg, provider):
  ss = frappe.get_doc("SMS Provider", provider)
  if not ss.enabled:
    msgprint(_("SMS Provider is disabled."))
    return "Fail"
  # Check Timing
  allow_now = False
  if ss.timing:
    for t in ss.timing:
      if get_time(t.from_time) <= get_time(nowtime()) <= get_time(t.to_time):
        allow_now=True
        break 
  else:
    allow_now = True
  if not allow_now:
    msgprint(_("SMS Provider doesn't alow to send sms now."))
    return "Fail"
  headers = get_headers(ss)

  args = {ss.message_parameter: re.sub(
      r'\s+', ' ', safe_decode(arg.get('message')))}
  for d in ss.get("parameters"):
    if not d.header:
      args[d.parameter] = d.value

  success_list = []
  for d in arg.get('receiver_list'):
    args[ss.receiver_parameter] = d
    url = ss.sms_gateway_url
    if "%(" in url:
      url = ss.sms_gateway_url % args
    status = send_request(url, {} if "%(" in ss.sms_gateway_url else args,
                          headers, ss.use_post, ss.get('request_as_json'))
    if 200 <= status < 300:
      success_list.append(d)
  log_doc = None
  if len(success_list) > 0:
    args.update(arg)
    if frappe.db.exists("DocType", "SMS Log"):
      log_doc = create_sms_log(args, success_list, provider=provider)
    if arg.get('success_msg'):
      frappe.msgprint(_("SMS sent to following numbers: {0}").format(
          "\n" + "\n".join(success_list)))
  return log_doc and log_doc or success_list


def send_request(gateway_url, params, headers=None, use_post=False, request_as_json=False):
  import requests

  if not headers:
    headers = get_headers()
  if use_post:
    if request_as_json:
      response = requests.post(gateway_url, headers=headers, json=params)
    else:
      response = requests.post(gateway_url, headers=headers, data=params)
  else:
    response = requests.get(gateway_url, headers=headers, params=params)
  response.raise_for_status()
  return response.status_code


def safe_decode(string, encoding='utf-8'):
  try:
    string = string.decode(encoding)
  except Exception:
    pass
  return string

# Create SMS Log
# =========================================================


def create_sms_log(args, sent_to, provider=None):
  sl = frappe.new_doc('SMS Log')
  sl.sent_on = now_datetime()
  sl.message = safe_decode(args['message'])
  sl.no_of_requested_sms = len(args['receiver_list'])
  sl.requested_numbers = "\n".join(args['receiver_list'])
  sl.no_of_sent_sms = len(sent_to)
  sl.sent_to = "\n".join(sent_to)
  sl.provider = provider
  sl.flags.ignore_permissions = True
  sl.submit()
  return sl


def get_sms_recipients_for_notification(notification, doc, context=None):
  if notification.channel != "SMS":
    return []
  recipients = []
  for row in notification.sms_recipients or []:
    if row.target_type == "Mobile Nos":
      recipients.extend(row.mobile_nos.split("\n"))
    elif row.target_type == "Field":
      if doc.get(row.field_name):
        recipients.append(doc.get(row.field_name))
    elif row.target_type == "User" and row.get("target_user"):
      user = frappe.get_cached_doc("User", row.get("target_user"))
      if user.mobile_no or user.phone:
        recipients.append(user.mobile_no or user.phone)
    elif row.target_type == "Role" and row.get('target_role'):
      mobiles = frappe.db.sql(""" select distinct coalesce(usr.mobile_no, usr.phone) from tabUser usr
      right join `tabHas Role` hr on hr.parent=usr.name
      where hr.role="{}" and hr.parenttype="User" and coalesce(usr.mobile_no, usr.phone, "") != ""
      """.format(row.get('target_role')))
      recipients.extend([x[0] for x in mobiles])
    elif row.target_type == "cmd":
      try:
        attr = frappe.get_attr(row.get("cmd"))
        param = row.get("cmd_param")
        if "{" in param:
          param = frappe.render_template(param, context)
        param = ast.literal_eval(param)

        r = attr(**param)
        if isinstance(r, string_types):
          recipients.append(r)
        elif isinstance(r, list):
          recipients.extend(r)
        else:
          frappe.throw("SMS Recipient CMD should return either string or list")
      except Exception:
        frappe.log_error(title="SMS Recipients CMD Error",
                         message=frappe.get_traceback())
        frappe.msgprint("SMS Recipients CMD Error")
  return recipients
