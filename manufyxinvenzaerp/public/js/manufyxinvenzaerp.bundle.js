// App-wide desk bundle.
//
// Everything listed in hooks.py's app_include_js goes through here rather than
// being referenced as a bare /assets/.../js/<file>.js path.
//
// Why: a bare public asset is served at a fixed URL with `Cache-Control:
// max-age=43200`, so an edit to it is invisible to any browser that loaded the
// old copy within the last 12 hours -- there is nothing in the URL to tell them
// apart. That is not theoretical: the ERP Manual page shipped its renderer and
// its page script in the same commit, and every browser that had already cached
// the PREVIOUS renderer kept serving it, so the page loaded a file that lacked
// manufyx_render_manual_tree and rendered nothing but its own "renderer not
// loaded" error. Server-side everything checked out, which is what made it
// stubborn to pin down.
//
// A *.bundle.js file is compiled by esbuild to a content-hashed filename
// (manufyxinvenzaerp.bundle.<HASH>.js) recorded in assets.json, which Frappe
// resolves at render time -- so the URL changes whenever the contents change and
// browsers can never serve a stale copy. Frappe's own bundles work this way.
//
// Note that a bundle executes in esbuild's module scope, NOT global scope: a file
// added here must attach anything it wants globally to `window` itself (see the
// tail of manual_renderer.js).

import "./mfx_buttons.js";
import "./rate_schedule.js";
import "./item.js";
import "./storage_location.js";
import "./weighment.js";
import "./manual_renderer.js";
