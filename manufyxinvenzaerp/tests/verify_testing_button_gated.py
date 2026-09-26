"""The Operation Entry "Testing" button only appears where testing is switched on.

"Add All Drawing" fills the Consumption Log with one row per drawing at its full
available quantity in a single click. That is a data-entry shortcut, not a step in
the real process, and it sat on every Operation Entry where an operator could
reach it.

It is now shown only where Manufyxinvenza Settings enables Auto Purchase -- the
same switch that reveals the Auto Purchase section on Material Planning. Both are
testing conveniences, so one switch governs both and there is nothing new for
anyone to know about.

Run: bench --site manufact execute manufyxinvenzaerp.tests.verify_testing_button_gated.run
"""

import json
import re
import subprocess

import frappe

checks = []
FLAG = "auto_purchase_from_material_planning"


def check(label, got, want):
    ok = got == want
    checks.append(ok)
    print("  %-4s %-58s got=%r want=%r" % ("OK" if ok else "FAIL", label, got, want))


def _soe_script():
    """The Operation Entry client script exactly as setup.py installs it."""
    src = open(frappe.get_app_path("manufyxinvenzaerp", "setup.py")).read()
    m = re.search(r'SOE_CLIENT_SCRIPT = """(.*?)\n"""', src, re.S)
    return m.group(1).encode().decode("unicode_escape")


# The handler run in node against a stubbed form. Clicking twice used to log every
# drawing twice; since 2026-09-26 it adds only what the log does not yet hold.
_HARNESS = r"""
function flt(v,p){v=parseFloat(v)||0;return p==null?v:Math.round(v*Math.pow(10,p))/Math.pow(10,p);}
var __=function(s){return s;};
var frappe={msgprint:function(){},show_alert:function(){},datetime:{get_today:function(){return "2026-09-26";}}};
function _calc_consumption_weight_kg(){} function _sync_drawing_nos(){}
function click(details, log){
  var f={doc:{drawing_details:details,consumption_log:log},refresh_field:function(){},dirty:function(){}};
  f.add_child=function(t,v){v.doctype="x";f.doc.consumption_log.push(v);return v;};
  _add_all_drawing_to_log(f);
  return f.doc.consumption_log.map(function(r){return [r.drawing,r.qty_nos];});
}
var two=[{drawing:"D1",available_to_consume_nos:5},{drawing:"D2",available_to_consume_nos:4}];
var once=click(two,[]);
console.log(JSON.stringify({
  empty: once,
  again: click(two, once.map(function(r){return {drawing:r[0],qty_nos:r[1]};})),
  partial: click(two,[{drawing:"D1",qty_nos:3}]),
  dup_rows: click([{drawing:"D1",available_to_consume_nos:5},{drawing:"D1",available_to_consume_nos:2}],
                  [{drawing:"D1",qty_nos:6}])
}));
"""


def _simulate(js):
    i = js.index("function _add_all_drawing_to_log")
    j = js.index("\nfunction ", i + 10)
    out = subprocess.run(["node", "-e", js[i:j] + _HARNESS], capture_output=True, text=True)
    return json.loads(out.stdout) if out.returncode == 0 else {"error": out.stderr}


def run():
    js = _soe_script()

    print("=== clicking adds only what is still pending ===")
    r = _simulate(js)
    check("empty log: every drawing at its full quantity", r.get("empty"), [["D1", 5], ["D2", 4]])
    check("second click adds nothing", r.get("again"), [["D1", 5], ["D2", 4]])
    check("3 of 5 logged: one new row of 2, D2 in full", r.get("partial"),
          [["D1", 3], ["D1", 2], ["D2", 4]])
    check("a drawing on two rows shares one logged total", r.get("dup_rows"), [["D1", 6], ["D1", 1]])

    print("=== the switch exists and is the Auto Purchase one ===")
    meta = frappe.get_meta("Manufyxinvenza Settings")
    field = meta.get_field(FLAG)
    check("the setting is there", bool(field), True)
    check("it is a checkbox", field.fieldtype if field else None, "Check")

    print()
    print("=== the button is behind it ===")
    check("the setting is read before the button is added",
          'get_single_value("Manufyxinvenza Settings", "%s")' % FLAG in js, True)
    check("nothing is added when it is off", "if (!enabled) return;" in js, True)
    check("the button is inside the callback",
          js.index("if (!enabled) return;") < js.index('__("Add Pending Drawing to Log")'), True)
    # A direct button since 2026-09-26 -- the client asked for one click, not
    # Testing -> Add All Drawing.
    check("it is a direct button, not in a Testing group", '__("Testing")' in js, False)

    print()
    print("=== the conditions it already had are kept ===")
    check("draft only", "frm.doc.docstatus === 0" in js, True)
    check("not on an unsaved document", "!frm.is_new()" in js, True)

    print()
    print("=== the same switch governs Material Planning's Auto Purchase ===")
    mp = open(frappe.get_app_path(
        "manufyxinvenzaerp", "production_management", "doctype",
        "material_planning", "material_planning.js")).read()
    check("Material Planning reads the same setting",
          'get_single_value("Manufyxinvenza Settings", "%s")' % FLAG in mp, True)
    check("and hides its section the same way", "if (!enabled) return;" in mp, True)

    print()
    print("=== what the setting says on this site right now ===")
    enabled = frappe.db.get_single_value("Manufyxinvenza Settings", FLAG)
    print("   %s = %r" % (FLAG, enabled))
    print("   so the Testing button is currently %s"
          % ("SHOWN" if enabled else "HIDDEN"))
    print("   (switch it in Manufyxinvenza Settings to change both this and the")
    print("    Auto Purchase section on Material Planning)")

    print()
    print("=== the installed Client Script matches the source ===")
    installed = frappe.db.get_value(
        "Client Script", {"dt": "Supplier Operation Entry"}, "script") or ""
    if not installed:
        print("   (no Client Script installed yet -- runs on the next migrate)")
    else:
        check("the live script is gated too",
              'get_single_value("Manufyxinvenza Settings", "%s")' % FLAG in installed, True)

    print()
    print("=== SUMMARY ===")
    if all(checks):
        print("ALL %d CHECKS PASSED" % len(checks))
    else:
        print("%d of %d CHECKS FAILED" % (checks.count(False), len(checks)))
