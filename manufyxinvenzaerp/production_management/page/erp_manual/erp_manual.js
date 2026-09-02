// ERP Manual — doctype-wise reference, tree-navigated.
//
// Replaces the two per-doctype "Manual" buttons (Material Planning, Material Issue
// Plan). Content there was walkthrough-style, meant to be read start to finish;
// this page is doctype-wise instead, one category per doctype, each table/topic as
// a sub-tab under it -- meant to be looked something up in, not read straight
// through. The old walkthroughs are migrated in as the fully-populated categories
// below; the client's own nav sketch (Item / Sales Order / Drawing as siblings,
// Material Planning and Production Plan each expanding to their own tables) is
// followed for the categories not yet written up, kept visible as "Coming Soon"
// so the intended shape is there even before the content is.
//
// Expanded since: Item gained the Batch Record, Inspection gained the call/round
// mechanics and the incoming-goods (Purchase Receipt) path, Reports gained the four
// reports it never covered, and two categories were added -- Purchase & Procurement
// (Material Request -> RFQ/SQ -> Purchase Order -> Purchase Receipt, the chain that
// starts where Material Planning finds a shortfall) and Reference (every status flow
// in one place, plus Manufyxinvenza Settings). Nothing that was here was removed.
//
// Then: the job work order gained a real status flow (Open -> Working -> Completed,
// driven by its operations and the Material Issue Plan's Final Stock Entry) and the
// Open MIP / Open Job Work Order buttons; Supplier Operation Entry gained the rules
// around closing one -- what Completed now requires, the confirm-and-submit prompt,
// and why an operation cannot be cancelled on its own.
//
// Then: Process Loss. The excess return became a movement out of the supplier rather
// than stock created from nothing, the final Stock Entry began consuming what the
// drawings needed rather than everything sent, and the difference between the two --
// what the supplier cannot account for -- became a declared write-off with a reason.
// Billed to Consume was removed in the same pass; that material is Process Loss now.
//
// Then: Delivery Challan (Gate Pass) -- the pre-printed pad as a document. Its own
// category, because it is not part of the production chain: it records what left the
// gate for any reason, delivery-note or subcontract alike, and moves no stock at all.
// Returnable passes are chased through Return Entries that net off row by row, and the
// status goes Overdue on its own once the return date passes.
//
// Layout/tree/scrollspy come from the shared renderer
// (public/js/manual_renderer.js) via manufyx_render_manual_tree(); this file is
// only the content. A leaf uses the same shape as the old flat manuals: {id,
// title, kicker, purpose, fields[], steps[], calcs[], examples[], notes[],
// buttons[]}, everything optional.

frappe.pages["erp-manual"].on_page_load = function (wrapper) {
	let page = frappe.ui.make_app_page({
		parent: wrapper,
		title: "ERP Manual",
		single_column: true,
	});

	// The renderer lives in public/js/manual_renderer.js, pulled in app-wide via
	// app_include_js. If that asset has not been rebuilt/served, the page would
	// otherwise fail with a bare ReferenceError and render blank -- say so plainly
	// instead, because the fix (bench build + a hard refresh) is not guessable from
	// an empty screen.
	if (typeof manufyx_render_manual_tree !== "function") {
		page.main.html(
			'<div style="margin:24px;padding:20px;border:1px solid #C6462F;border-radius:10px;background:#FBEAE6">' +
				"<b>" + __("Manual renderer not loaded") + "</b><br>" +
				__("manufyx_render_manual_tree is undefined — manufyxinvenzaerp.bundle.js did not load. Run <code>bench build --app manufyxinvenzaerp</code> and hard-refresh (Ctrl+Shift+R).") +
				"</div>"
		);
		return;
	}

	manufyx_render_manual_tree(page, {
		heading: __("ERP Manual"),
		intro: __("Doctype by doctype, table by table — pick a category on the left."),
		welcome: {
			title: __("Manufacturing, Start to Finish"),
			body: __(
				"The flow this ERP drives: <b>Material Planning</b> works out where every raw " +
				"material is coming from, <b>Production Plan</b> schedules the job and its " +
				"operations, <b>Job work order</b> is the single execution document for all of " +
				"them, <b>Material Issue Plan</b> is where reserved stock physically leaves the " +
				"warehouse, and each operation runs through <b>Supplier Operation Entry</b> — " +
				"gated by <b>Inspection</b> wherever QC sign-off is required. Upstream of all of it, " +
				"<b>Item</b>, <b>Sales Order</b>, <b>Drawing</b> and <b>BOM</b> are where a job is " +
				"defined in the first place, and <b>Purchase &amp; Procurement</b> is how anything " +
				"Material Planning could not find in stock gets bought. Every category on the left " +
				"is written up; <b>Reference</b> holds every status flow and the site settings, and " +
				"<b>Glossary</b> the terms used throughout."
			),
		},
		categories: ERP_MANUAL_CATEGORIES,
	});
};

// ─── Categories not yet written up — kept visible so the intended shape of the
// manual is there ahead of the content (client's own request: "later we will add
// more details about it"). Each renders as "Coming Soon" until filled in. ────────
// Sales Order — where a job starts. The BOM sheet is uploaded here and turned into
// Drawings and BOMs before Material Planning ever sees it.
const ERP_MANUAL_SALES_ORDER_CHILDREN = [
	{
		id: "so-overview",
		title: "From Sales Order to BOM",
		kicker: "The whole upload flow",
		purpose:
			"Everything downstream — Material Planning, purchasing, transfers, production — is built " +
			"from Drawings and BOMs. Both are created here, from one Excel sheet attached to the " +
			"Sales Order. Get this stage right and the rest follows; get it wrong and every later " +
			"stage inherits the mistake.",
		steps: [
			"Create the Sales Order and enter <b>every finished goods item</b> in the Items table. Not just one line — each FG item the customer has ordered needs its own row.",
			"Prepare the BOM sheet. <b>The same FG item codes must appear in the sheet's FG Item column.</b> A code in the sheet that is not on the order (or spelled differently) has nothing to attach to.",
			"Attach the sheet to <b>BOM Excel File</b> on the Sales Order and save.",
			"<b>Load Items</b> — reads the sheet and stages every drawing and its raw materials onto the order.",
			"<b>Verify Raw Materials</b> — checks what was staged. Fix anything it reports, then run it again.",
			"<b>Create Drawing</b> — creates a Drawing document per drawing in the sheet.",
			"<b>Submit</b> the Sales Order, then <b>Submit Drawing</b>.",
			"<b>Mark as Final Revision</b> — freezes the drawings as the version to build from.",
			"<b>Create and Submit BOM</b> — one BOM per drawing, ready for Material Planning.",
		],
		notes: [
			"<b>Two ways to get the sheet.</b> <b>Download Template</b> (on the Sales Order, before a file is attached) gives you an empty sheet with the correct column headers. " +
			"To see one filled in properly, download the worked sample: " +
			"<a href='/assets/manufyxinvenzaerp/files/Sample_BOM_Sheet.xlsx' download " +
			"style='font-weight:600'>Sample BOM Sheet (filled)</a> — a real 22-drawing sheet with " +
			"100 raw-material rows, showing how the header columns repeat down every row of a drawing.",
			"<b>Column headers must match.</b> The importer finds columns by name, not position, so you may reorder them — but a renamed or missing header is simply not read. Assembly Group, Customer Drawing Number, DUNO/Mark No, FG Item, Total Qty, Total Weight (KG), Nature of Work, Rate Schedule, Item No, Material Code, Grade, Thickness, Width, Length, Reqd Raw Material Qty.",
			"<b>One row per raw material, not per drawing.</b> A drawing needing three materials takes three rows, and its header columns (drawing number, DUNO, FG item, quantities, Nature of Work, Rate Schedule) repeat identically on all three. The importer groups them by Customer Drawing Number.",
		],
		buttons: [
			{ name: "Download Template", note: "An empty sheet with the right headers. Only shown before a file is attached." },
			{ name: "Load Items", note: "Parses the attached sheet onto the order. Disabled once drawings exist, so a reload cannot contradict what was already created." },
			{ name: "Clear Items", note: "Removes staged rows so you can correct the sheet and load again. Rows that already have a Drawing are kept." },
		],
	},
	{
		id: "so-verify",
		title: "Verify Raw Materials",
		kicker: "The gate before drawings",
		purpose:
			"Checks everything staged from the sheet and refuses to pass until it is right. This is " +
			"deliberately strict: a bad row here becomes a bad Drawing, a bad BOM, and a wrong " +
			"requirement in Material Planning, and by then it is far harder to see where it came from. " +
			"The full list of what it checks is below — everything the weight formula reads, whether " +
			"the value is absent when it is needed or present when it is not.",
		fields: [
			{ name: "Material Code", note: "Present on the row, and exists in the Item master. A typo here is the most common failure." },
			{ name: "Parent Item Group", note: "The Item master must say <b>Structurals</b>, <b>Plates</b> or <b>Nuts and Bolts</b>. Any other value — or none — means no weight can be calculated, so the row is rejected rather than staged weighing zero. It must also still match what the row was staged with: if the Item was re-grouped after the upload, you are told to load the sheet again." },
			{ name: "Unit Weight", note: "Must be set on the Item master. It is not in the sheet — it comes from the Item — and without it the formula produces nothing." },
			{ name: "Dimensions the formula needs", note: "<b>Structurals:</b> Length. <b>Plates:</b> Length, Width and Thickness. <b>Nuts and Bolts:</b> none. Missing any of them is reported against the drawing and Item No it came from." },
			{ name: "Dimensions the formula does not use", note: "A value here is reported too. A Structural's weight is Length × Unit Weight × Sec Qty — Thickness and Width take no part — and a bolt uses no dimension at all. Anything typed into an unused column is not harmless: it is carried into the Drawing, the BOM and Material Planning as a real requirement that the delivered material can never match." },
			{ name: "Reqd Raw Material Qty", note: "Must be more than zero, for every group. This is the Sec Qty (pieces) the formula multiplies by — a blank column produces a row weighing nothing." },
			{ name: "Calculated weight", note: "The last check: the row's Kg is recalculated from its current dimensions and the Item master's Unit Weight. Zero is refused, and a figure that no longer agrees with what was staged means the Item master changed after the upload — load the sheet again." },
			{ name: "Nature of Work", note: "Must already exist in the Nature of Work master. Checked by name exactly as typed." },
			{ name: "Rate Schedule", note: "Must already exist in the Rate Schedule master — e.g. RS- O/S-001 A. Checked by name; there is no format rule, so your numbering can change freely." },
			{ name: "FG Item", note: "Every drawing needs one, and it must exist in the Item master." },
			{ name: "DUNO/Mark No", note: "Must be filled in on each drawing." },
			{ name: "Total Qty", note: "Must be more than zero. A blank is otherwise read as one piece, and every total on the drawing would be calculated for a single unit." },
			{ name: "Rows per drawing", note: "A drawing staged with no raw-material rows at all is reported by name." },
		],
		examples: [
			{
				type: "dont",
				label: "ISMB250 with a Thickness of 10",
				text: "A beam is a Structural — its weight is Length × Unit Weight × Sec Qty, so it has no Thickness to give. " +
					"One line of a 100-row sheet had 10 typed into the Thickness column. The weight was still correct, " +
					"so nothing looked wrong: the 10 travelled into the Drawing, the BOM and Material Planning as part of " +
					"the requirement, and when the beam was received with no thickness it could not be matched to it. " +
					"<b>Now reported at this step</b>, naming the drawing, the Item No and the column to clear.",
			},
			{
				type: "do",
				label: "The same row, correct",
				text: "Material Code ISMB250, Length 879.1, Thickness and Width left empty, Reqd Raw Material Qty 1, " +
					"and a Unit Weight of 37.3 on the Item master. 879.1 / 1000 × 37.3 × 1 = <b>32.79 Kg</b>.",
			},
		],
		notes: [
			"<b>It blocks, it does not warn.</b> Anything reported has to be corrected in the sheet (or the master record created) before the flow can continue. Correct the sheet, Clear Items, Load Items again, and re-verify.",
			"<b>Load Items warns about unused columns too</b>, as soon as the sheet is read, so you can see it against the file still in front of you. Only this step blocks.",
			"<b>Why unknown values still reach this screen.</b> The importer stages rows with a direct insert that skips link checking, on purpose — so a wrong Rate Schedule lands in the table and can be reported <i>against the drawing it came from</i>. Rejecting during the upload would abort the whole file over one cell and tell you nothing about where it was.",
			"<b>Rows whose Drawing already exists are not re-checked.</b> They are locked at that point and the check skips them, so correcting the sheet for a later drawing can never fail an order that is already part-built.",
			"<b>Blank is allowed</b> for Nature of Work and Rate Schedule. Neither is mandatory on a Drawing, and older imports predate both columns.",
		],
		buttons: [
			{ name: "Verify Raw Materials", note: "Runs every check above. Passing sets the order's verified flag; failing lists each problem <b>led by the row it is on</b> — <i>Raw Materials row 100 · …</i> or <i>Drawing List row 22 · …</i> — followed by the drawing, Material Code and Item No. The table is named because both are on this order and row 22 of one is not row 22 of the other." },
		],
	},
	{
		id: "so-weights",
		title: "Customer Weight vs Calculated Weight",
		kicker: "Two numbers, two meanings",
		purpose:
			"Every drawing carries two weights and they are not two attempts at the same figure. " +
			"One is typed in from the sheet and describes the finished part. The other is worked out " +
			"by the system from the raw materials listed under that drawing. They are supposed to " +
			"differ — what matters is which way round.",
		fields: [
			{ name: "Customer Provided Weight (Kg)", note: "On the drawing row. Comes from the sheet's <b>Total Weight (KG)</b> column — what the finished, fabricated piece weighs. Typed in, never calculated, and editable." },
			{ name: "Calculated Weight (Kg) — drawing row", note: "<b>Auto calculated.</b> What the raw materials listed under that drawing add up to. Read-only, filled the moment Load Items runs and recalculated on every save." },
			{ name: "Calculated Weight (Kg) — raw material row", note: "<b>Auto calculated.</b> That one material's weight: <i>Length ÷ 1000 × Unit Weight × Reqd Sec Qty</i> for Structurals, <i>Length ÷ 1000 × Width ÷ 1000 × Thickness × Unit Weight × Reqd Sec Qty</i> for Plates. Unit Weight comes from the Item master, not the sheet." },
			{ name: "Calculated Total Weight (Kg)", note: "<b>Auto calculated.</b> The row's weight × the drawing's Total Quantity — what the whole drawing quantity consumes of that one material." },
		],
		calcs: [
			{
				title: "Drawing 1B16 — material 1 of 3",
				item: "ISMB250", group: "Structurals",
				length: 879.1, sec_qty: 1, unit_weight: 37.3,
				formula: "(Length ÷ 1000) × Unit Weight × Sec Qty  =  (879.1 ÷ 1000) × 37.3 × 1",
				result: "32.790",
			},
			{
				title: "Drawing 1B16 — material 2 of 3",
				item: "ISA100", group: "Structurals",
				length: 190, sec_qty: 4, unit_weight: 14.9,
				formula: "(Length ÷ 1000) × Unit Weight × Sec Qty  =  (190 ÷ 1000) × 14.9 × 4",
				result: "11.324",
			},
			{
				title: "Drawing 1B16 — material 3 of 3",
				item: "PLATE10", group: "Plates",
				length: 210.81, width: 201, thickness: 10, sec_qty: 1, unit_weight: 7.85,
				formula: "(L ÷ 1000) × (W ÷ 1000) × Thickness × Unit Weight × Sec Qty  =  (210.81÷1000) × (201÷1000) × 10 × 7.85 × 1",
				result: "3.326",
				note: "<b>Drawing total:</b> 32.790 + 11.324 + 3.326 = <b>47.44 Kg</b> calculated, against a " +
					"Customer Provided Weight of <b>42.90 Kg</b> — a difference of <b>+4.54 Kg (+10.6%)</b>.",
			},
		],
		examples: [
			{
				type: "do",
				label: "Calculated above customer weight — normal",
				text: "To make a 42.9 Kg part you consume 47.44 Kg of steel. The stock is cut down to " +
					"the finished piece, so the raw material is the heavier of the two. Small drawings " +
					"show a larger percentage than big ones — a broadly fixed allowance is a small " +
					"fraction of a 900 Kg beam and a large fraction of a 43 Kg one.",
			},
			{
				type: "dont",
				label: "Calculated below customer weight — look at it",
				text: "The materials listed cannot physically produce the part: you are asking for a " +
					"finished piece heavier than the steel it is cut from. Something is wrong in the " +
					"sheet — a missing row, a length short by a decimal place, or a wrong Sec Qty. " +
					"The summary panel names any drawing in this state.",
			},
		],
		notes: [
			"<b>The gap is not an error and nothing needs correcting for it.</b> The system is built on it: the excess tracking in Material Issue Plan follows exactly this chain — customer weight, then planned raw material, then the weight of the batch actually mapped.",
			"<b>Where each is shown.</b> Per material on the Raw Materials row, per drawing on the Drawing List row, and totalled for the whole order in the summary panel beside the BOM file.",
			"<b>Nothing here is typed except the customer's figure.</b> Every Calculated field is read-only and recomputed from the dimensions and the Item master's Unit Weight, so it can never drift from the rows it summarises.",
		],
	},
	{
		id: "so-summary",
		title: "Loaded Sheet Summary",
		kicker: "The panel beside the file",
		purpose:
			"A running summary of what the sheet actually produced, shown next to the file it came " +
			"from. It reads the staged rows directly in the browser, so it follows an edit in the " +
			"grid immediately — no save, no reload.",
		fields: [
			{ name: "Drawings", note: "How many drawings the sheet produced, and how many already have a Drawing document created." },
			{ name: "Raw material rows", note: "Total staged rows, then the same total split by group — e.g. 50 Plates · 50 Structurals. A group you did not expect to see is worth a second look." },
			{ name: "Customer weight", note: "The sheet's Total Weight (KG) added up across every drawing." },
			{ name: "Calculated weight", note: "What all the listed raw materials add up to across every drawing." },
			{ name: "Difference", note: "Calculated minus customer, in Kg and as a percentage. Positive is the normal direction." },
			{ name: "Below customer weight", note: "Any drawing whose raw material weighs <i>less</i> than the finished piece, named by Mark No. <b>None</b> in green is what you want to see." },
			{ name: "Raw materials", note: "Verified or Not verified — the same state as the button above the Raw Materials table." },
		],
		notes: [
			"<b>It is a summary, not a check.</b> Verify Raw Materials is what blocks; this panel is for seeing at a glance whether the sheet loaded into the shape you expected before you commit to creating drawings.",
			"<b>Read the difference as a direction, not a target.</b> Whether +2% is right for your fabrication is an engineering judgement. The panel only reports it — and calls out the one case that is always wrong, a drawing whose material weighs less than the part.",
		],
	},
	{
		id: "so-drawings",
		title: "Create Drawing, Final Revision, BOM",
		kicker: "Turning the sheet into documents",
		purpose:
			"The three build steps. Each processes in batches with a live progress dialog, so a large " +
			"order does not time out and you can watch it work.",
		steps: [
			"<b>Create Drawing</b> — one Drawing document per Customer Drawing Number, carrying its DUNO/Mark No, FG item, customer weight, Nature of Work, Rate Schedule and its full raw-material list. Created as drafts, so they can still be corrected.",
			"<b>Submit Drawing</b> — locks each drawing. The Sales Order itself must be submitted before the next step.",
			"<b>Mark as Final Revision</b> — marks the drawings as the version production will be built from. A BOM can only be created from a submitted, Final Revision drawing.",
			"<b>Create and Submit BOM</b> — one BOM per drawing, from that drawing's raw materials. These are what Material Planning pulls requirements from.",
			"<b>View Drawing</b> — what the group offers once the BOMs are done. Each step appears only while there is work left at it, and never two at once, so the menu is a to-do list rather than a list of everything the button could ever do.",
		],
		notes: [
			"<b>The progress dialog is live.</b> It shows how many are done, how many are pending, elapsed time, an estimate of what is left and the current rate — refreshed every second. The estimate is measured from the run itself, so it is rough at first and tightens as it goes.",
			"<b>BOM creation is the slow step</b>, at roughly a tenth of a second per drawing — a few seconds for a small order, around a minute for 500 drawings. That is ERPNext's own BOM validation and costing, not something the upload is doing badly. Leave the dialog open; it is working.",
			"<b>To revise one drawing, use its own Create Revision button</b> — not the standard Cancel button on the toolbar. Cancelling by hand makes Frappe follow the link into the Sales Order and out again to every other drawing on it, and offer to <i>Cancel All Documents</i>: on an order with twenty-two drawings that is twenty-two cancelled to revise one, behind a dialog that looks routine. Create Revision cancels the one drawing, opens revision n+1 as a draft and leaves every sibling submitted. The Sales Order row is released while the revision is a draft and re-attaches when you submit it, so the order never shows a drawing nobody has signed off.",
			"<b>Drawings are created in batches</b> and can be run again safely: a drawing that already exists is skipped, not duplicated. If a batch fails, fix the cause and re-run — the ones already created stay.",
		],
		buttons: [
			{ name: "Create Drawing", note: "Creates the Drawing documents. Skips any drawing number that already has one." },
			{ name: "Submit Drawing", note: "Submits the created drawings." },
			{ name: "Mark as Final Revision", note: "Requires the Sales Order to be submitted first." },
			{ name: "Create Revision", note: "On the Drawing itself, on any submitted drawing. It cancels the drawing and opens its next revision as a draft in one step, and takes you straight to it. Use this rather than the standard <b>Cancel</b> button — see the note below." },
			{ name: "(cancelling a drawing)", note: "Cancel a Drawing and its DUNO row lets go of it, so the row goes back to being a DUNO with no drawing against it — which is what it now describes. <b>Amend</b> that drawing and submit the amendment and the row picks up the new revision by itself. Nothing has to be re-pointed by hand, and the order can be saved and submitted again." },
			{ name: "Create and Submit BOM", note: "Creates and submits one BOM per drawing. The longest step on a large order. It appears only once <b>every</b> drawing waiting to be marked final has been marked — the two are consecutive steps, not a choice, and making BOMs for whichever drawings happened to be ready leaves the rest behind while the toolbar reads as though the job is done." },
			{ name: "View Drawing", note: "Takes the place of Create and Submit BOM once every Final Revision drawing has a submitted BOM. It confirms that the drawing stage is finished — <i>“Drawings and BOMs are created — ready to proceed to Material Planning”</i> — and opens this order's drawings. There is nothing left to create at that point, so the group stops offering it." },
			{ name: "Submit BOM", note: "Submits BOMs that were created but left in draft. Nothing in this app creates a draft BOM any more — the old <b>Create BOM</b> button did, and it was removed for exactly that reason — so this is only for drafts made by hand or left over from before." },
		],
	},
];

// Drawing — one per drawing in the uploaded sheet. Everything downstream measures
// itself against the numbers held here.
const ERP_MANUAL_DRAWING_CHILDREN = [
	{
		id: "drw-what",
		title: "What a Drawing Holds",
		kicker: "One per drawing in the sheet",
		purpose:
			"Every drawing in the BOM sheet becomes one Drawing document. It carries who the job " +
			"is for, what is being made, and the full raw-material list for it — and it is the " +
			"master those figures are corrected on later. Production Plans, Job Work Orders and " +
			"Material Issue Plans all take their copy of the customer weight from here.",
		fields: [
			{ name: "Sales Order, Customer, Customer No, Project, Cust PO No", note: "Pulled from the Sales Order the sheet was uploaded to — not typed again." },
			{ name: "Customer Drawing Number / DUNO / Mark No", note: "From the sheet. The Customer Drawing Number is what groups its raw-material rows together during import." },
			{ name: "FG Item Code / Name / Description", note: "The finished-goods item, from the sheet's FG Item column — which is why the same code must be on the Sales Order's Items table." },
			{ name: "No of Qty to Manufacture", note: "From the sheet's Total Qty. Every row's totals are multiplied by this." },
			{ name: "Nature of Work", note: "From the sheet. Must already exist in the Nature of Work master." },
			{ name: "Rate Schedule / Type", note: "The schedule comes from the sheet; Type is read from the schedule itself, along with Job Nature, Details, Work Content, Job Reference and Rate per Kg." },
			{ name: "Rev No", note: "Revision number. 0 on the original — see Revisions below." },
		],
		notes: [
			"<b>The raw-material rows live on the Raw Materials tab.</b> Each carries Item No, Material Code, Grade, the dimensions, and Reqd Raw Material Qty (the Sec Qty) — exactly as uploaded.",
		],
	},
	{
		id: "drw-calcs",
		title: "What Is Calculated, and How",
		kicker: "Per row, and per drawing",
		purpose:
			"Nothing weight-related is typed on a Drawing. Every figure below is recalculated on " +
			"every save from the dimensions and the item's Unit Weight, so a corrected dimension " +
			"always flows through to the totals.",
		calcs: [
			{
				title: "Row weight for a Structural — Qty",
				item: "ISMB400", group: "Structurals",
				length: 6936, sec_qty: 2, unit_weight: 61.6,
				formula: "(Length ÷ 1000) × Unit Weight × Sec Qty  =  (6936 ÷ 1000) × 61.6 × 2",
				result: "854.51",
			},
			{
				title: "Row weight for a Plate — Qty (uses Width and Thickness too)",
				item: "PLATE10", group: "Plates",
				length: 424.68, width: 180, thickness: 10, sec_qty: 2,
				formula: "(L ÷ 1000) × (W ÷ 1000) × Thickness × Unit Weight × Sec Qty  =  (424.68÷1000) × (180÷1000) × 10 × 7.85 × 2",
				result: "12.00",
			},
		],
		steps: [
			"<b>Total Sec Qty</b> = Sec Qty × No of Qty to Manufacture. One drawing built twice needs twice the pieces.",
			"<b>Total Qty</b> = the same weight formula run against Total Sec Qty — not the row weight multiplied, so rounding cannot drift.",
			"<b>Total Weight</b> (drawing level) = the sum of every row's weight, taking Qty where the row's UOM is Kg and Sec Qty where the secondary UOM is Kg.",
			"<b>Nuts and Bolts reverse.</b> There Qty is the count and Sec Qty is the weight, so Total Qty = Qty × No of Qty to Manufacture and Total Sec Qty = Total Qty × Unit Weight.",
		],
		notes: [
			"<b>The comparison you want is in Totals.</b> <b>Total Weight</b> is what the drawing's own raw materials add up to — our engineering figure. <b>Customer Provided Weight</b> is what the customer stated, brought in from the sheet's Total Weight (KG). The gap between them is the difference every downstream document measures excess against.",
			"<b>A missing Unit Weight breaks the chain silently.</b> With no Unit Weight on the Item master, the formula yields nothing and the row weighs zero. Verify Raw Materials on the Sales Order catches this before drawings are ever created.",
		],
	},
	{
		id: "drw-weight",
		title: "Changing the Customer Weight",
		kicker: "Correct it here, once",
		purpose:
			"When the customer revises a weight, change it on the Drawing and nowhere else. The " +
			"field itself is read-only on purpose: editing copies one by one is how documents end " +
			"up disagreeing. Use Update Customer Weight and every copy is rewritten together.",
		steps: [
			"Open the Drawing and press <b>Update Customer Weight</b>.",
			"Enter the new figure. The old value, the new one, who changed it and when are written to the drawing's own <b>Weight Change Log</b> — so the history is on the document, not in someone's memory.",
			"Everything below is then updated in the same operation.",
		],
		fields: [
			{ name: "Drawing", note: "Customer Provided Weight itself, plus a Weight Change Log row recording the change." },
			{ name: "Sales Order", note: "The DUNO Item's Total Weight — the value every downstream document originally read from. The order is re-saved, so its raw-material quantities recalculate." },
			{ name: "Sales Order — Difference Kg", note: "Recomputed for that drawing/DUNO pair, which is what makes the new excess visible." },
			{ name: "Production Plan", note: "Customer Weight Kg on the Production Plan Item for this drawing." },
			{ name: "Job Work Order", note: "Customer Weight Kg on its drawing row, and the order's own total re-summed from those rows." },
			{ name: "Material Issue Plan", note: "Customer Weight Kg on its drawing row, then the whole weight summary refreshed." },
		],
		notes: [
			"<b>Prefer the sheet.</b> If anything else changed alongside the weight — a dimension, a quantity, a material — correct the BOM sheet on the Sales Order and load it again instead. Use this button only when the weight alone has moved and nothing else about the drawing has.",
			"<b>Excess follows automatically.</b> Excess is the gap between what was planned or mapped and what the drawing says is needed — so once the customer weight moves, the difference is recomputed and the excess figures downstream reflect it without anything else being touched.",
			"<b>Batches are deliberately left alone.</b> Reserved and mapped batches are NOT re-allocated, because a weight change should not silently move steel that is already committed or shipped. If the new weight means a different allocation, unreserve and reserve again by hand in Material Planning.",
			"<b>Work Order is not updated</b> — it is standard ERPNext in this app and carries no copy of this figure.",
			"<b>The same weight is rejected.</b> Entering the value it already has does nothing but add noise to the log, so it is refused.",
		],
		buttons: [
			{ name: "Update Customer Weight", note: "The only supported way to change it. Writes the Drawing, the Sales Order and every downstream copy in one go, with an audit row." },
		],
	},
	{
		id: "drw-revisions",
		title: "Revisions",
		kicker: "Rev No",
		purpose:
			"Corrections are made in the BOM sheet on the Sales Order, not on the Drawing. The " +
			"sheet is the master input: raw materials, dimensions, quantities and weights all come " +
			"from it, so a revision means updating the sheet and loading it again — that way every " +
			"changed detail travels together instead of being patched one field at a time.",
		notes: [
			"<b>Do not rework a Drawing by hand.</b> When a revision arrives, or the customer changes a weight, update the BOM sheet attached to the Sales Order and load it again. The Drawing carries the raw-material list as well as the weight, and editing figures on it one at a time leaves the sheet and the drawing telling different stories.",
			"<b>Rev No is derived, never typed.</b> It is read from the document being amended, so the sequence cannot be broken by hand.",
			"<b>Amending does not move the BOM.</b> A BOM already created from the earlier revision stays as it is — create a BOM from the new revision when it is ready, and it is that BOM which Material Planning should be pointed at.",
		],
		steps: [
			"<b>Cancel</b> the submitted Drawing.",
			"<b>Amend</b> it. Frappe creates a new document linked back to the cancelled one.",
			"<b>Rev No</b> is set automatically: the previous drawing's Rev No plus one. An original imported drawing is Rev 0, its first amendment Rev 1, and so on.",
			"Correct what changed, then submit and Mark as Final Revision as before.",
		],
	},
];

// BOM — created from a Drawing, one per drawing. Read-only in practice: everything on
// it is derived, and nothing here is where costs are decided.
const ERP_MANUAL_BOM_CHILDREN = [
	{
		id: "bom-what",
		title: "What the BOM Holds",
		kicker: "One per drawing",
		purpose:
			"Created by Create and Submit BOM on the Sales Order — one BOM per Drawing, built " +
			"entirely from that drawing's own data. Nothing on it is typed. It exists so Material " +
			"Planning has something to pull requirements from, and so every requirement stays " +
			"traceable back to the drawing and sheet it came from.",
		fields: [
			{ name: "Item / Item Name", note: "The finished-goods item, from the drawing's FG Item — originally the sheet's FG Item column." },
			{ name: "Quantity", note: "The drawing's No of Qty to Manufacture, which came from the sheet's Total Qty." },
			{ name: "Drawing / DUNO Mark No / Customer Drawing Number", note: "Carried across so any requirement can be traced back to its drawing and its row in the sheet." },
			{ name: "Project / Company / Currency", note: "Project from the drawing; company and its default currency from your setup." },
			{ name: "Items table", note: "One row per raw material on the drawing — Material Code, the dimensions, Unit Weight, Sec Qty and Sec UOM, Item Group and Item Number, all as uploaded. Qty is the drawing's Total Qty for that row, so it already accounts for how many are being made." },
		],
		notes: [
			"<b>Everything here came from the sheet.</b> The BOM is the third copy of the same data — sheet, then Drawing, then BOM. That is why corrections belong in the sheet: change it there and reload, and all three agree. Editing a BOM by hand leaves it disagreeing with the drawing it was built from.",
		],
	},
	{
		id: "bom-operations",
		title: "Operations and Workstations",
		kicker: "Added automatically",
		purpose:
			"Every BOM gets the standard routing attached automatically — you do not choose it and " +
			"you do not need to maintain it. It is there for information and for tracing work back " +
			"afterwards, not because anything asks you to plan it here.",
		steps: [
			"<b>With Operations</b> is ticked and <b>Routing</b> is set to <b>Standard Manufacturing Routing</b> on every BOM, without being asked for.",
			"That routing carries five operations, in order: <b>Fit-up, Welding, Final, Blasting, Painting</b>.",
			"Each operation has a workstation of the same name, created alongside it.",
			"The real sequence for a job is decided later, on the Production Plan's Process Planning table — which operations actually run, who performs each one, and which are skipped.",
		],
		notes: [
			"<b>Material Issue is no longer one of them.</b> Issuing material is what the Material Issue Plan does, and carrying it as an operation as well made every job start on a step nobody worked. Jobs raised before this are untouched and still show it; only new BOMs and new jobs are built without it.",
			"<b>No item has a default BOM.</b> Standard ERPNext nominates one BOM per item and stamps it on the Item master, so every Sales Order line for that item arrives carrying it. Here an item is a shape of steel and one finished-goods item has hundreds of BOMs — one per drawing — so nominating one is meaningless, and a Sales Order will not even open once the nominated BOM is gone. The field is kept empty deliberately; you do not need to set it and should not.",
			"<b>Informational only.</b> The operations on a BOM do not drive anything. Production is driven by the Production Plan's Process Planning rows, which create one Operation Entry each. The BOM's copy is there so the standard route is visible on the document and can be looked back at.",
			"<b>Operating cost is not used.</b> The times on the routing are placeholders and the BOM's Operating Cost stays at zero — labour is not costed here.",
		],
	},
	{
		id: "bom-costing",
		title: "Rates and Costing",
		kicker: "An estimate, not the cost",
		purpose:
			"The value on a BOM is an estimate for reference only. The real raw-material cost of a " +
			"job comes from the stock that is actually issued to it, at the rate that stock was " +
			"actually valued at — which is known at Stock Entry time, not here.",
		fields: [
			{ name: "Rate Of Materials Based On", note: "Set to Valuation Rate. Each row is priced at the item's valuation at the moment the BOM is built." },
			{ name: "Raw Material Cost / Total Cost", note: "The estimate that follows from those rates." },
			{ name: "Operating Cost", note: "Zero — see Operations above." },
		],
		notes: [
			"<b>Treat the BOM value as indicative.</b> It is a snapshot of valuation on the day the BOM was created. Valuation moves with every purchase, so the same BOM built a month later would show a different figure for identical material.",
			"<b>The actual cost is recorded on the Stock Entry.</b> When material is issued against a job, the rate on that entry is what the stock was really worth, and that is what the raw-material cost of the job is calculated from. If you need to know what a job cost, look at its Stock Entries, not its BOM.",
			"<b>A zero rate on a BOM means zero valuation, not free material.</b> If stock was received without a rate, its valuation is zero and every BOM using it will show zero for those rows. Fix it at the receipt — the BOM is only reporting what it was told.",
		],
	},
];

// ─── Item — custom fields, validation rules, UOM config, batch naming. ──────────
const ERP_MANUAL_ITEM_CHILDREN = [
	{
		id: "item-overview",
		kind: "overview",
		title: "How the Item Master Works Here",
		kicker: "Start here",
		purpose:
			"The Item master is where every raw material and finished-goods item is configured. " +
			"This app adds a small set of custom fields on top of standard ERPNext — they drive weight " +
			"calculations, UOM rules, batch naming, and inspection gating across every module. " +
			"Get them right on the item and everything downstream works automatically; leave them " +
			"wrong and the formulas produce nothing, or wrong numbers.",
	},
	{
		id: "item-custom-fields",
		title: "Custom Fields",
		kicker: "What was added and why",
		purpose:
			"Six custom fields added to the Item master. Together they classify the item, " +
			"configure its UOM pair, set the weight constant the Kg formula needs, control " +
			"how batches are named at receipt, and flag whether an incoming batch must pass " +
			"inspection before it can be reserved in Material Planning.",
		fields: [
			{
				name: "Material Spec",
				note: "Free-text specification for the item — grade, standard, or any note that " +
					"identifies the material beyond its name. Optional; does not drive any calculation.",
			},
			{
				name: "Parent Item Group",
				note: "<b>Mandatory.</b> A Link to an Item Group marked as a group (not a leaf). " +
					"The three values that matter here are <b>Structurals</b>, <b>Plates</b>, and " +
					"<b>Nuts and Bolts</b> — everything the weight formula, the UOM rules, and the " +
					"batch-naming pattern does is branched on this field. Any other value means the " +
					"item is treated as a non-formula item (no Kg calculation). " +
					"<b>Locked</b> once transactions exist — cannot be changed after a Stock Ledger " +
					"Entry, submitted Purchase Order or submitted Sales Order references this item.",
			},
			{
				name: "Unit Weight",
				note: "The item's weight constant — <b>kg/metre for Structurals</b> (e.g. ISMB400 = 61.6 kg/m), " +
					"<b>density factor for Plates</b> (always 7.85 for steel plates, unitless — the formula " +
					"multiplies Length × Width × Thickness × 7.85). " +
					"<b>Mandatory for Structurals, Plates, and Nuts and Bolts</b> — without it the formula " +
					"produces zero and every downstream Kg figure is wrong. " +
					"<b>Locked</b> once transactions exist.",
			},
			{
				name: "Secondary UOM",
				note: "The item's second unit. For <b>Structurals and Plates</b> this is <b>Nos</b> (pieces); " +
					"for <b>Nuts and Bolts</b> it is <b>Kg</b>. Set automatically when you choose a Parent " +
					"Item Group. <b>Locked</b> once transactions exist.",
			},
			{
				name: "Item Calculation Type",
				note: "<b>Read-only, set automatically.</b> Shows which formula branch this item uses: " +
					"<b>Formula Weight Calculation</b> for Structurals and Plates (Kg derived from dimensions); " +
					"<b>Normal Weight Calculation</b> for Nuts and Bolts (Kg entered directly via Unit Weight × Nos). " +
					"You cannot set this field by hand — it follows Parent Item Group.",
			},
			{
				name: "Custom Batch Abbreviation",
				note: "<b>Only shown when Has Batch No is ticked.</b> A short code used as the prefix of " +
					"every batch created for this item on a Purchase Receipt or Stock Entry — e.g. " +
					"<b>ISMB400</b>, <b>PLT10</b>, <b>ISA100</b>. " +
					"<b>Mandatory for Structurals and Plates</b> when Has Batch No is on. " +
					"<b>Locked</b> once any batch exists for this item — see Batch Naming below.",
			},
			{
				name: "Inspection Required (Purchase Receipt)",
				note: "A checkbox. When ticked, every Purchase Receipt for this item enters an " +
					"inspection workflow — batches received cannot be reserved in Material Planning " +
					"until the linked Inspection Entry is Completed. " +
					"Leave it unticked for items you receive without an incoming-QC step.",
			},
		],
		notes: [
			"<b>Locked fields.</b> Five fields are locked once the item has any transaction (Stock Ledger Entry, " +
				"submitted Purchase Order, submitted Sales Order): Parent Item Group, Default Unit of Measure, " +
				"Unit Weight, Secondary UOM, and Custom Batch Abbreviation. Changing them after transactions " +
				"exist would make historical stock balances and Kg calculations inconsistent — the system " +
				"blocks the save with a clear message naming the locked field.",
			"<b>Item Group filter follows Parent Item Group.</b> When you pick a Parent Item Group, the " +
				"Item Group dropdown automatically filters to show only leaf groups whose parent matches — " +
				"so you cannot accidentally put an ISMB under Plates.",
		],
	},
	{
		id: "item-uom-rules",
		title: "UOM Configuration Rules",
		kicker: "Which UOM goes where",
		purpose:
			"The system enforces a fixed UOM pair per item group. Setting Parent Item Group " +
			"auto-fills the correct values; the server then validates them on save so a wrong " +
			"combination is caught immediately rather than silently producing wrong formulas.",
		fields: [
			{
				name: "Structurals (e.g. ISMB400, ISA100)",
				note: "<b>Default UOM (stock_uom): Kg.</b> <b>Secondary UOM: Nos.</b> " +
					"Weight formula: (Length ÷ 1000) × Unit Weight × Sec Qty.",
			},
			{
				name: "Plates (e.g. PLATE10)",
				note: "<b>Default UOM: Kg.</b> <b>Secondary UOM: Nos.</b> " +
					"Weight formula: (L ÷ 1000) × (W ÷ 1000) × Thickness × Unit Weight × Sec Qty.",
			},
			{
				name: "Nuts and Bolts",
				note: "<b>Default UOM: Nos.</b> <b>Secondary UOM: Kg.</b> " +
					"No dimension formula — Qty is the count (Nos), Sec Qty is the weight in Kg (Nos × Unit Weight).",
			},
		],
		calcs: [
			{
				title: "Structural — ISMB400, Unit Weight 61.6 kg/m",
				item: "ISMB400", group: "Structurals",
				length: 6936, sec_qty: 2, unit_weight: 61.6,
				formula: "(Length ÷ 1000) × Unit Weight × Sec Qty  =  (6936 ÷ 1000) × 61.6 × 2",
				result: "854.51",
			},
			{
				title: "Plate — PLATE10, Unit Weight 7.85",
				item: "PLATE10", group: "Plates",
				length: 500, width: 500, thickness: 3, sec_qty: 52, unit_weight: 7.85,
				formula: "(L ÷ 1000) × (W ÷ 1000) × Thickness × Unit Weight × Sec Qty  =  (0.5) × (0.5) × 3 × 7.85 × 52",
				result: "306.15",
			},
		],
		notes: [
			"<b>Choosing Parent Item Group auto-fills the UOM pair.</b> You do not need to set " +
				"Default UOM or Secondary UOM manually — picking the group sets both instantly in the form.",
			"<b>The server validates both fields on save.</b> If you override the auto-filled values " +
				"with the wrong UOM, the save is blocked with a specific message — e.g. " +
				"\"System is configured for Primary UOM as KG for Structurals. Select Default UOM as Kg.\"",
			"<b>Nuts and Bolts reverses the pair.</b> For fasteners, Nos is the primary stock unit and " +
				"Kg is secondary — the formula runs in reverse: Qty (Nos) × Unit Weight = Sec Qty (Kg). " +
				"This is why the unit_weight on a bolt is weight-per-piece, not weight-per-metre.",
		],
	},
	{
		id: "item-batch-config",
		title: "Batch Configuration and Naming",
		kicker: "How batches get their names",
		purpose:
			"For Structurals and Plates, batches are created automatically at Purchase Receipt " +
			"and their names are built from the item's Custom Batch Abbreviation plus the " +
			"dimensions received. The name encodes exactly what the batch is — length, width, " +
			"thickness — so you can identify a batch without opening it.",
		fields: [
			{
				name: "Has Batch No",
				note: "Standard ERPNext field. Must be ticked for Structurals and Plates. When ticked " +
					"and the item is in a formula group, <b>Create New Batch</b> is forced on and " +
					"<b>locked to read-only</b> — batch creation is always automatic for these items.",
			},
			{
				name: "Custom Batch Abbreviation",
				note: "The prefix every batch for this item starts with. Keep it short and unique — " +
					"it is prepended to the dimension segments that follow. Examples: ISMB400, ISA100, PLT10.",
			},
		],
		steps: [
			"When a Purchase Receipt for a batch-tracked item is submitted, a batch is auto-created for each line.",
			"The batch name is built as: <b>[Abbreviation]-[T{thickness}]-[L{length}]-[W{width}]-R[receipt suffix]</b>. " +
				"Segments whose dimension is zero are omitted — a beam has no thickness, so T is skipped.",
			"The receipt suffix is the last 3 digits of the PR number — e.g. PR-26-00006 → <b>006</b>.",
			"If the generated name already exists a counter is appended: <b>-2</b>, <b>-3</b>, etc.",
		],
		examples: [
			{
				type: "do",
				label: "ISMB400, Length 12000mm, from PR-26-00006",
				text: "Abbreviation: ISMB400. No thickness, no width. → <b>ISMB400-L12000-R006</b>.",
			},
			{
				type: "do",
				label: "PLATE10, Thickness 3mm, Length 500mm, Width 500mm, from PR-26-00006",
				text: "Abbreviation: PLT10. Thickness 3, Length 500, Width 500. → <b>PLT10-T3-L500-W500-R006</b>.",
			},
			{
				type: "do",
				label: "Stock Entry (Repack/Material Receipt) batch",
				text: "Same pattern, but the suffix uses the SE number with a leading SR — " +
					"<b>ISMB400-L5136-SR007</b>. Used when excess material is booked back in via a return entry.",
			},
			{
				type: "dont",
				label: "Sec Qty (Nos) is 0 on the Purchase Receipt line",
				text: "The batch will be blocked from being created. Structurals and Plates are always " +
					"counted in Nos — a batch with Sec Qty 0 breaks the Kg→Nos allocation in Material Planning. " +
					"Fix the PR line (enter the correct piece count) before submitting.",
			},
		],
		notes: [
			"<b>Custom Batch Abbreviation cannot be changed once any batch exists</b> for the item. " +
				"All existing batches start with the old prefix — changing it would leave them with a " +
				"name that no longer matches the current item setting. Create a new item code if the " +
				"abbreviation genuinely needs to change.",
			"<b>Dimension fields on the batch are set at creation and can only be changed via specific " +
				"system operations</b> (e.g. a Cut Sheet W2 resize after a transfer). They are not free-edit " +
				"fields.",
		],
	},
	{
		id: "item-inspection",
		title: "Inspection Required Flag",
		kicker: "Gating batches in Material Planning",
		purpose:
			"When Inspection Required (Purchase Receipt) is ticked on an item, every batch " +
			"received for it must pass a completed Inspection Entry before it can be reserved " +
			"in Material Planning. This prevents uncommitted or rejected material from being " +
			"allocated to a job before QC has signed off.",
		steps: [
			"Tick <b>Inspection Required (Purchase Receipt)</b> on the Item master and save.",
			"Receive the item on a Purchase Receipt. An Inspection Call workflow opens on the receipt " +
				"— create the Inspection Entry, run the quality check, and submit it as <b>Completed</b>.",
			"Once the linked Purchase Receipt's Inspection Status is <b>Completed</b>, Material Planning " +
				"allows the batch to be reserved. Until then, any Reserve attempt skips the batch and " +
				"reports it as <b>blocked pending inspection</b>.",
		],
		fields: [
			{ name: "Inspection Required (Purchase Receipt)", note: "The checkbox on the Item master." },
			{ name: "Inspection Status (on Purchase Receipt)", note: "Open / Working / Completed — set by the Inspection Entry workflow. Only Completed unblocks the batch." },
		],
		notes: [
			"<b>Fail-open for non-PR batches.</b> A batch with no traceable source Purchase Receipt " +
				"(e.g. one created from a Material Receipt Stock Entry for an excess return) is never " +
				"blocked — even if its item has Inspection Required ticked. The gate only applies to " +
				"incoming purchased material.",
			"<b>Items without the flag are never blocked</b>, regardless of any receipt's inspection status.",
			"<b>Reassigning a blocked batch</b> in Material Planning produces a warning (not a hard error) " +
				"— the batch assignment is saved but the row stays unreserved until inspection is complete.",
		],
	},
	{
		id: "item-group-fields",
		title: "Item Group Custom Fields",
		kicker: "Dimension rules per group",
		purpose:
			"Three custom fields on the Item Group master control which dimension columns are " +
			"mandatory when a drawing row or BOM import row uses an item from that group. These " +
			"are set on the group, not on each item — so adding a new material code to an " +
			"existing group automatically inherits the right dimension rules.",
		fields: [
			{ name: "Mandatory Thickness", note: "When checked on a group, every import/drawing row for items in this group must have a Thickness value. Plates is the primary example." },
			{ name: "Mandatory Length Value", note: "Required length dimension — applies to both Structurals and Plates." },
			{ name: "Mandatory Width Value", note: "Required width dimension — Plates only." },
		],
		notes: [
			"<b>These fields only appear on group-level Item Groups</b> (is_group = 1), not on leaf groups.",
			"<b>Verify Raw Materials on the Sales Order reads these flags</b> to know which dimensions " +
				"to check for completeness and which to flag as unused (a Structural must have Length but " +
				"must NOT have Thickness or Width — having either is reported as an error).",
		],
	},
	{
		id: "item-batch-record",
		title: "The Batch Record",
		kicker: "What a batch carries, and where its name comes from",
		purpose:
			"A batch is the physical piece — one bar, one plate, one bundle — and it is what " +
			"Material Planning reserves against. Batches are not created by hand: submitting a " +
			"Purchase Receipt creates one per receipt line, named from the item's own Custom Batch " +
			"Abbreviation plus the dimensions on that line, so the name alone tells you what the " +
			"piece is.",
		fields: [
			{ name: "Length / Width / Thickness", note: "Copied from the Purchase Receipt line that created this batch, and <b>read-only</b> afterwards. Exact Match in Material Planning compares these three numbers against the requirement, so a batch whose dimensions were edited after the fact would silently match the wrong rows." },
			{ name: "Sec Qty / Sec UOM", note: "How many physical pieces this batch holds, and in what unit (normally Nos). This is what every Kg → Nos calculation downstream divides by." },
			{ name: "Batch Remarks", note: "Read-only. Carried over from the Inspection Call remarks recorded against this batch's source Purchase Receipt, so a QC note stays attached to the piece rather than living only on the receipt. It is copied onward onto Stock Entry rows that move this batch." },
			{ name: "Reservations", note: "A live panel, not a stored field — shows every Material Planning currently holding a claim on this batch and how much each one has taken. This is the quickest way to answer “who has already spoken for this bar?”" },
			{ name: "Source MIP Excess Row", note: "Set only on batches created by an Excess Return Entry. Records which Material Issue Plan excess row this off-cut came back from, so a returned remnant can be traced to the job that produced it." },
			{ name: "Existing Supplier Invoice No / Existing Invoice Wt / Existing Inward Date", note: "Read-only supplier-document details captured at receipt, kept on the batch for traceability back to the paperwork the material arrived on." },
		],
		steps: [
			"On Purchase Receipt submit, ERPNext creates one batch per stock ledger entry, and this app names it before it is inserted.",
			"The name is built as <b>Abbreviation-T{thickness}-L{length}-W{width}-R{receipt suffix}</b>, dropping any dimension the line does not carry — a Structural has no Width or Thickness, so its name is just Abbreviation-L…-R….",
			"If that exact name already exists, <b>-2</b> (then -3, and so on) is appended, so two identical pieces received on different days never collide.",
			"Dimensions, Sec Qty and Sec UOM are copied from the receipt line onto the batch at the same moment.",
		],
		examples: [
			{
				type: "do",
				label: "A plate batch name reads back as the plate",
				text: "Item <b>PLATE10</b> with Custom Batch Abbreviation <code>PL10</code>, received 10 mm thick × 6000 long × 1500 wide on receipt …-00042, becomes <b>PL10-T10-L6000-W1500-R00042</b> — thickness, length, width and the receipt it came in on, all readable without opening anything.",
			},
			{
				type: "dont",
				label: "Don't put two identical-dimension rows for the same item on one receipt",
				text: "The batch being created is matched back to its line by finding the first row of that item that has no batch yet. Two rows with identical Length, Width and Thickness cannot be told apart, and the receipt is refused with a message telling you to give them distinct dimensions or split the receipt — deliberately loud, because a batch that silently took the wrong line's piece count breaks Kg → Nos allocation later with no visible error.",
			},
		],
		notes: [
			"An item with no <b>Custom Batch Abbreviation</b> set gets ERPNext's default batch naming instead — see <b>Batch Configuration and Naming</b> above.",
			"Batches are also created by Stock Entry, not just Purchase Receipt: a Repack raised by a Cut Sheet, or a Material Receipt, both name their batches the same way, using the Stock Entry number as the suffix instead of the receipt number.",
			"Structurals and Plates are always piece-tracked. A batch of either that somehow resolved to Sec Qty 0 is rejected outright rather than saved, because nothing downstream can divide by it.",
		],
	},
];

const ERP_MANUAL_STUB_CATEGORIES = [
	{ id: "item", label: "Item", children: ERP_MANUAL_ITEM_CHILDREN },
	{ id: "sales-order", label: "Sales Order", children: ERP_MANUAL_SALES_ORDER_CHILDREN },
	{ id: "drawing", label: "Drawing", children: ERP_MANUAL_DRAWING_CHILDREN },
];

// ─── Material Planning — migrated verbatim from the old Material Planning manual,
// one child per table/topic exactly as that page's sidebar listed them. ─────────
const ERP_MANUAL_MATERIAL_PLANNING_CHILDREN = [
	{
		id: "overview",
		kind: "overview",
		title: "How Material Planning Works",
		kicker: "Start here",
		purpose:
			"Material Planning answers one question for every raw material a job needs: " +
			"“where is this going to come from?” It checks your real warehouse stock, " +
			"and sorts every requirement into one of three buckets — already have the exact " +
			"piece, have the item but need to cut/substitute, or don't have it at all and need " +
			"to buy it. Everything downstream (reservations, purchasing, allocation once stock " +
			"arrives) flows from that first sort.",
	},
	{
		id: "select-boms",
		title: "Selected BOMs",
		kicker: "Choosing what to plan",
		purpose:
			"Where a plan gets its scope. Pick the Sales Order, then choose which of its BOMs " +
			"this plan covers — all of them, or a few. Everything the plan later does is limited " +
			"to what you select here.",
		steps: [
			"Set <b>Sales Order</b> in the Import BOMs section.",
			"The picker lists every submitted BOM on that order, with its drawing and DUNO/Mark No. Tick <b>all of them</b>, or only the ones this plan is for.",
			"The chosen BOMs land in the <b>BOM Items</b> table, each carrying its drawing, DUNO, customer, Customer Provided Weight and Planned Weight.",
			"Press <b>Get Raw Materials</b> to pull in every raw material those BOMs need.",
		],
		notes: [
			"<b>One plan per order, or several — both are supported.</b> A single plan can cover a whole sales order, which is the simplest way to buy in bulk: requirements for the same item consolidate across every drawing on the order. Or split the order across several plans — by area, by phase, by delivery date — and each plans and reserves independently. Nothing forces one plan per order.",
			"<b>Only submitted BOMs appear.</b> A BOM still in draft is not offered, because its quantities can still change. Submit it on the Sales Order first.",
			"<b>Adding BOMs later is fine.</b> Select more and press Get Raw Materials again; the new requirements are added. Reservations already made are not disturbed.",
		],
		buttons: [
			{ name: "Get Raw Materials", note: "Pulls every raw material from the selected BOMs into the Raw Materials table. This is the starting point for everything else." },
		],
	},
	{
		id: "raw-materials",
		title: "Raw Materials",
		kicker: "Table 1 of 7",
		purpose:
			"The starting point. This is the full list of raw materials your selected BOMs " +
			"actually need — pulled in with the “Get Raw Materials” button. At this " +
			"stage nothing has been checked against stock yet; it's purely a requirement list, " +
			"item by item, drawing by drawing.",
		fields: [
			{ name: "Item Code / Item Name", note: "What's needed." },
			{ name: "Source BOM / Drawing / DUNO / Mark No / Cust Drawing No", note: "Where this requirement came from — keeps every row traceable back to a specific drawing." },
			{ name: "Item Group", note: "Structurals, Plates, or Nuts and Bolts — this decides which Kg formula applies everywhere downstream." },
			{ name: "Length / Width / Thickness (mm)", note: "The dimensions this requirement needs. Plates use all three; Structurals only really uses Length; Nuts and Bolts uses neither." },
			{ name: "Sec Qty", note: "Number of pieces (Nos) needed." },
			{ name: "Weight (qty)", note: "The required weight in Kg, computed from the dimensions above." },
			{ name: "Available Qty / Shortage Qty", note: "Filled in once stock is checked." },
			{ name: "Unit Weight", note: "The item's weight per metre (or per Nos), from the Item master — the constant every Kg formula multiplies by." },
		],
		calcs: [
			{
				title: "How the requirement's own Weight (Kg) is calculated",
				item: "ISA100", group: "Structurals",
				length: 3000, sec_qty: 5, unit_weight: 14.9,
				formula: "(Length ÷ 1000) × Unit Weight × Sec Qty  =  (3000 ÷ 1000) × 14.9 × 5",
				result: "223.5",
			},
			{
				title: "Same idea for a Plate (uses Width and Thickness too)",
				item: "PLATE10", group: "Plates",
				length: 500, width: 500, thickness: 3, sec_qty: 52,
				formula: "(L ÷ 1000) × (W ÷ 1000) × Thickness × Unit Weight × Sec Qty  =  (500÷1000) × (500÷1000) × 3 × 7.85 × 52",
				result: "306.15",
			},
		],
		buttons: [
			{ name: "Get Raw Materials", note: "Pulls the requirement list in from the BOMs you selected on the Selected BOMs tab." },
			{ name: "Verify Raw Materials", note: "A sanity pass over the pulled-in rows before you commit to checking stock." },
			{ name: "Check Stock Availability", note: "The big one. Runs the whole matching engine and splits every row into Available Raw Materials, Material Mapping, or Unavailable Items — explained in the next sections. <b>Safe to re-run once a purchase is under way:</b> rows whose item is already on an active Material Request are carried over untouched, and the popup says how many it kept. Without that they were wiped, taking with them the only rows the eventual Purchase Receipt could have matched — so the goods arrived and the plan still showed everything unmapped." },
		],
	},
	{
		id: "exact-match",
		title: "Available Raw Materials (Exact Match)",
		kicker: "Table 2 of 7",
		purpose:
			"Batches that are already the exact size you need, sitting in the warehouse right " +
			"now. No cutting, no substitution, no manual decision — just reserve it and move on. " +
			"This is the best-case outcome of “Check Stock Availability.”",
		fields: [
			{ name: "Item Code / DUNO / Cust Drawing No", note: "Same traceability as Raw Materials." },
			{ name: "Batch No", note: "The specific batch that matched — auto-selected, you don't pick this by hand here." },
			{ name: "Length / Width / Thickness", note: "The batch's own dimensions — identical to what was required, which is exactly why it landed in this table." },
			{ name: "Overall Required Qty", note: "The full quantity this drawing row needs." },
			{ name: "Allocated Qty in Batch (Required Qty)", note: "How much of this specific batch is being claimed for this row — can be less than Overall Required Qty if the batch had to be split across several drawings." },
			{ name: "Available Qty in Batch", note: "How much free stock that batch actually had at match time." },
			{ name: "Reserved / Reserved Qty / Shortfall Qty / Reserved On", note: "Filled in once you reserve this row (see Reserve/Unreserve below)." },
			{ name: "CNC Process", note: "Ticks that this piece needs CNC cutting before it goes to the supplier — full explanation and example below." },
			{ name: "Skip Auto Suggest Batch", note: "Tick this and save to send the row over to Material Mapping instead — useful if you'd rather save this exact-match batch for a different job." },
		],
		steps: [
			"“Check Stock Availability” compares each required row's Length/Width/Thickness against every batch of that item currently free in your warehouse.",
			"A batch only counts as an Exact Match if its own Length, Width, AND Thickness are EQUAL to what's required — not “close enough,” not “bigger and could be cut down.” Exactly equal.",
			"If more than one batch could match, the largest free one is tried first, and if one batch can't cover the whole requirement, the remainder is filled from the next batch — you may see two rows for the same drawing requirement, one per batch used.",
		],
		calcs: [
			{
				title: "Exact match found",
				item: "ISA100", group: "Structurals",
				length: 12000, width: 0, thickness: 0, sec_qty: 5, unit_weight: 14.9,
				formula: "Batch ISA100-L12000-SR001 is 12000mm — exactly what's required (12000 = 12000, 0 = 0, 0 = 0). Kg = (12000÷1000) × 14.9 × 5",
				result: "894.0",
			},
		],
		examples: [
			{
				type: "do",
				label: "Exact match — auto-selected",
				text: "Required: ISA100, Length 12000mm. In stock: Batch ISA100-L12000-SR001, exactly 12000mm. → Same dimensions, so it's an exact match. The batch is auto-selected into this table, ready to reserve.",
			},
			{
				type: "dont",
				label: "Same item, wrong size — NOT auto-selected",
				text: "Required: ISA100, Length 5000mm. In stock: only ISA100-L12000-SR001 (12000mm). → Same item, plenty of stock — but the dimensions don't match exactly, so nothing gets auto-selected here. This requirement goes to Material Mapping instead, where you manually assign that 12000mm bar and the system works out how much of it (by weight) this 5000mm requirement will consume.",
			},
		],
		buttons: [
			{ name: "Reserve (grid button)", note: "Reserves every matched row in one go, with partial-stock awareness — you'll get a summary of what was fully reserved, partially covered, or blocked (e.g. a batch still waiting on inspection)." },
			{ name: "Unreserve (per row)", note: "Releases just that row's claim." },
		],
		notes: [
			"Reserving only ever claims the quantity ON THIS ROW — never the whole batch. Example: Batch ISA100-L12000-SR001 has 12,158.4 Kg free across the warehouse. This row only needs 894 Kg (the calculation above), so reserving it claims exactly 894 Kg. The remaining 11,264.4 Kg stays free — visible and reservable by any other row or any other Material Planning, right up until someone else claims it too.",
			"Reserving is a soft claim, not a physical stock movement — it just marks the quantity as spoken for so no other Material Planning can also claim it. The actual movement out of the warehouse happens later, during Transfer (from the Material Issue Plan).",
			"CNC Process — tick this when the piece needs CNC cutting/machining at your own facility before it's ready to send to the supplier. Instead of moving straight from stores to the supplier/WIP warehouse, a CNC-ticked row's material is sent first to the CNC Warehouse set on the Material Issue Plan (via its “To CNC Warehouse” button); once machining is done, the separate “CNC to Supplier/WIP” button forwards it on. Example: a 10mm plate batch needs laser cutting before subcontracted fabrication — tick CNC Process on its row, and it's routed through the CNC Warehouse first; un-ticked rows on the same plan transfer straight to the supplier as normal.",
		],
	},
	{
		id: "material-mapping",
		title: "Material Mapping (Alternate Stock)",
		kicker: "Table 3 of 7",
		purpose:
			"For everything that has SOME usable stock but isn't an exact-size match — a full-" +
			"length bar or plate that needs cutting down, a substitute (alternate) item, or " +
			"material recovered from another job's excess. This is where you (or an automatic " +
			"process) make the sizing/substitution decision by hand.",
		fields: [
			{ name: "Item Code / Required Qty / Required Sec Qty", note: "What's actually needed — unchanged from the original requirement." },
			{ name: "Length / Width / Thickness / Unit Weight", note: "The REQUIRED dimensions (not the batch's) — shown for reference so you know what you're covering." },
			{ name: "Assign Batch", note: "Pick any batch by hand — of this item or of a substitute — with no dimension-matching restriction, unlike Exact Match. <b>Only batches holding stock in this plan's Raw Materials Warehouse are offered</b>, with the item, the Kg available there and the batch's dimensions shown beside each one. Set the warehouse first: with it blank, nothing is offered." },
			{ name: "Status (Mapped / Not Mapped / Excess Mapped / Cut Sheet Mapped)", note: "At a glance, what state this row is in — see the Status legend below." },
			{ name: "Planned Item (from Batch)", note: "The item the assigned batch actually is — will differ from Item Code if you've substituted an alternate item." },
			{ name: "Batch Length / Width / Thickness / Unit Weight", note: "The ASSIGNED BATCH's own dimensions — this is what the Kg formula actually uses, not the required dimensions." },
			{ name: "Sec Qty (NOS) / Calc Qty (Kg)", note: "How many pieces you're taking from the batch, and the Kg that works out to." },
			{ name: "Reserve stock without dimensions", note: "Explained with a worked example below — one batch shared across several rows, and how it works on a Cut Sheet row." },
			{ name: "CNC Process", note: "Same meaning as on Available Raw Materials — see that section for the full example." },
			{ name: "Reserved / Reserved Qty / Shortfall Qty / Reserved On", note: "Same reservation bookkeeping as Exact Match — and the same rule: only the quantity ON THIS ROW gets reserved, never the whole batch." },
			{ name: "Batch Total / Reserved / Free Qty", note: "A live snapshot of that batch's stock position across the whole system, not just this row." },
			{ name: "(a note on warehouses)", note: "The batch list used to be unfiltered, so a plan built for one warehouse could be mapped to a batch sitting in another. The reservation went through — a reservation is paper — and the stock check then reported the whole requirement as a shortfall against a batch holding ten tonnes in the wrong shed. The list is now taken from the plan's own warehouse, so that combination cannot be chosen." },
		],
		calcs: [
			{
				title: "Assign Batch — dimensions ON (default), whole-bar consumption",
				item: "ISMB400", group: "Structurals",
				length: 12000, sec_qty: 1, unit_weight: 61.6,
				formula: "Only a full 12000mm bar is available; you assign it and set Sec Qty = 1 whole bar. Calc Qty = (12000÷1000) × 61.6 × 1",
				result: "739.2",
				note: "If the drawing only actually needed the weight of a 3000mm length (184.8 Kg), the rest of this 739.2 Kg is off-cut — tracked later as excess once the job physically cuts it, in Material Issue Plan's Excess Return, not here.",
			},
			{
				title: "“Reserve stock without dimensions” — ON, exact Kg, fractional pieces",
				item: "Alternate item (different profile)", group: "Structurals",
				length: 6000, sec_qty: "fractional, see below", unit_weight: 10,
				formula:
					"Requirement is 500 Kg. This batch's own shape gives Kg-per-piece = (6000÷1000) × 10 = 60 Kg. " +
					"Sec Nos = 500 ÷ 60 = 8.333 pieces. Reserved Kg = exactly 500",
				result: "500.0 Kg  (8.333 Nos)",
				note: "Nothing is rounded here. Planning reserves precisely the 500 Kg the drawing needs — never a gram more — so the rest of that bar stays free for other rows. Turning 8.333 into whole bars is a physical decision, taken at transfer time in the Material Issue Plan.",
			},
			{
				title: "Same batch shared by SEVERAL rows — each keeps its own exact share",
				item: "2 drawing rows, one shared bar", group: "Structurals",
				length: 1000, sec_qty: "2 rows, see below", unit_weight: 25.38,
				formula:
					"Kg-per-piece for this batch = (1000÷1000) × 25.38 = 25.38 Kg. " +
					"Row 1 needs 33 Kg → 33 ÷ 25.38 = 1.3 Nos. " +
					"Row 2 needs 33 Kg → 1.3 Nos. " +
					"Together: 66 Kg = 2.6 Nos reserved",
				result: "66.0 Kg  (2.6 Nos across 2 rows)",
				note: "Both rows keep their exact 33 Kg / 1.3 Nos. At transfer you can hand over 2.6 pieces-worth as calculated, or raise it to 3 whole pieces — that adds 0.4 × 25.38 = 10.15 Kg, and THAT surplus is what becomes excess to return. Planning stays honest; the rounding decision (and its excess) is recorded where the material physically moves.",
			},
			{
				title: "On a Cut Sheet row — the same tick, sized against ONE piece instead of the batch",
				item: "Plate 5mm (from a Cut Sheet)", group: "Plates",
				length: 500, sec_qty: 4, unit_weight: 7.85,
				formula:
					"W1 is 500 × 250 × 5 = 4.90625 Kg per piece. Requirement is 18 Kg. " +
					"Ticked: 18 ÷ 4.90625. Unticked, typing 4 pieces: 4 × 4.90625",
				result: "Ticked — 18.000 Kg (3.669 Nos)   ·   Unticked, 4 pieces — 19.625 Kg (1.625 Kg excess)",
				note: "Same rule as an ordinary batch, just measured against one Cut Sheet piece instead of the whole plate — see the Cut Sheet section for why that distinction matters.",
			},
		],
		examples: [
			{
				type: "do",
				label: "“Reserve stock without dimensions” — OFF (default)",
				text: "You assign a batch of the SAME item, just a different piece. The system expects the batch's own Length/Width/Thickness to make sense against what's required, and computes an exact Kg from those dimensions. Precise, dimension-driven — use this whenever the batch's dimensions genuinely describe what you're consuming.",
			},
			{
				type: "do",
				label: "“Reserve stock without dimensions” — ON",
				text: "One bar or sheet is being shared across several rows, or you're substituting a different profile (an Alternate Item). Tick this box and the row reserves its exact Required Kg, with Sec Nos shown as that weight in pieces of the assigned batch — fractional on purpose (2.5 stays 2.5). This is exactly what happens automatically when a Purchase Receipt fulfils a consolidated or alternate-item line — you'll see this box already ticked on rows created that way.",
			},
			{
				type: "dont",
				label: "Don't expect whole pieces at planning stage",
				text: "A fractional Sec Nos such as 2.5 or 8.333 is correct, not a bug — it is the exact weight the drawings need, expressed in pieces of the batch you assigned. Nothing rounds it up automatically any more. Use “Validate Stock” to see every fractional total at a glance, and settle them at transfer time.",
			},
		],
		notes: [
			"Where rounding now happens: NOWHERE automatically. Material Planning always reserves the exact Required Kg and reports Sec Nos as a plain fraction of the assigned batch. The only place a fraction becomes whole pieces is the Material Issue Plan transfer popup, where you type the number yourself — the system re-checks free stock for the new figure and books the extra weight as excess to return.",
			"Partial transfers are why fractions matter. A Material Planning covering 10 drawings feeds a separate Material Issue Plan per drawing, and each plan only pulls its own drawings' reserved rows. So a batch planned across 5 rows (8 Nos in total) may well present as 4.5 Nos when only 3 of those drawings are being issued — that is expected. Raise it to 5 in the transfer popup if you must hand over whole bars, and the 0.5 piece of surplus is recorded for return.",
			"Case 1 vs Case 2. Case 1 — leave “Reserve stock without dimensions” OFF, pick a batch and type Sec Qty yourself; the system reserves exactly that and never overwrites your number. Case 2 — tick it when one large bar or sheet serves several rows; the system derives the fractional Sec Nos for you from each row's required Kg.",
			"<b>A batch with nothing left is not a match.</b> Sharing one batch across several requirements leaves an arithmetic residue — 1061.609 Kg split between two 530.804 Kg rows leaves 0.001, and the next split leaves a fraction of that. A batch is treated as having free stock only above 0.001 Kg, so a batch consumed to the last kilo is offered to nobody. Before that rule, those crumbs became Exact Match rows asking for 0.000 Kg: nothing to reserve, nothing to transfer, and a stock-check message reporting matches that were not there.",
			"Status legend — “Mapped” (green): an ordinary purchased batch is assigned. “Excess Mapped” (blue): a real batch is assigned and it came back from another job as an off-cut. “Excess Mapped (At Supplier)” (blue): a historical status only. It came from Return Type, which no longer exists — an off-cut that never comes back is now written off as <b>Process Loss</b> on its own job, with a reason. Rows saved before that change keep this status and still count as mapped. “Excess Mapped (Pending Return)” (blue): fulfilled from another job's excess that HASN'T physically returned to stock yet, but is already promised to this row; the batch attaches itself automatically the day it does return. “Cut Sheet Mapped” (blue): fulfilled from a Cut Sheet's nesting plan, sized to the piece (W1), not the plate. “Not Mapped” (red): nothing assigned yet. Every blue status counts as mapped — it is material you already have a claim on, so it is included in the Difference in Kg figure and never sent back through purchasing.",
		],
		buttons: [
			{ name: "Reserve / Unreserve", note: "Same soft-claim mechanism as Available Raw Materials — works whether the row has a real batch, a Cut Sheet allocation, or an Excess Mapped claim." },
			{ name: "(what a transfer does to a reservation)", note: "A row gives up only what actually left the warehouse. Transfer 30 Kg of a 120 Kg reservation and the row keeps the other 90 — it is released outright only when the remainder reaches zero. Where several rows share one batch they give it up one at a time in document order, so whole reservations are left behind rather than every row being left holding a fraction it can never transfer cleanly. Cancelling a transfer puts back exactly what it took." },
			{
				name: "Excess Material  (tick on the row)",
				note: "Only appears on a row with NO batch — excess is a promise against a specific off-cut, not stock in your warehouse. Ticking it reveals <b>Select Item</b>, which opens the picker described in the Excess Material Mapping section.",
			},
			{
				name: "Cut Sheet  (tick on the row — read-only)",
				note: "You never tick this yourself: it appears by itself the moment you pick a batch that has a Cut Sheet against it, and names that sheet plus how many pieces are still free. A batch either has a nesting plan or it does not, and a row claiming otherwise would be describing steel that does not exist in that shape. The row then takes on the PIECE's dimensions (W1), not the whole plate's.",
			},
			{
				name: "Validate Stock  (top of the form)",
				note: "A read-only roll-up per item and batch: planned Kg, planned Sec Nos, how many drawings share that batch, the batch's own stock, and any shortfall. Fractional Sec Nos totals show in amber with the whole-piece figure beside them, and shortfalls in red. It changes nothing — it is the quickest way to see which batches still need a whole-piece decision before the job reaches transfer.",
			},
		],
	},
	{
		id: "cut-sheet",
		title: "Cut Sheet",
		kicker: "One nesting plan per plate, shared across jobs",
		purpose:
			"A plate arrives as one batch and gets cut into repeated pieces, leaving a remnant. " +
			"The Cut Sheet is where that plan is written down ONCE, against the batch: this " +
			"piece (W1), this many of them, this remnant (W2). Jobs then take pieces from it " +
			"the same way they reserve batch stock, and the same plate can serve several " +
			"Material Plannings. It is its own document — open it from the Cut Sheet list, not " +
			"from inside a Material Planning.",
		fields: [
			{ name: "Batch", note: "The physical plate being cut. One batch can have only ONE Cut Sheet — two plans for the same steel would each hand out material the other had already promised." },
			{ name: "Sheet (as received)", note: "Length/Width/Thickness/Sec Nos read straight from the batch, never typed, so the two can't disagree." },
			{ name: "W1 — Piece to Cut", note: "Length and Width of the piece. Thickness always comes from the batch: cutting changes Length and Width, never how thick the steel is." },
			{ name: "W1 Sec Nos (available)", note: "How many of that piece this plate yields. YOU enter this — a suggestion is offered from the geometry, but the nesting is your call. It is deliberately not derived from weight; see the worked example." },
			{ name: "Kg per Piece / W1 Total", note: "Calculated. One piece's weight, and all the pieces together." },
			{ name: "W2 — Balance", note: "What is left once the cutting is done. Entered by hand. Written onto the batch when the FIRST transfer from this sheet is submitted." },
			{ name: "Availability", note: "Allocated and Available, in both Sec Nos and Kg — what other jobs have taken and what is still free to claim." },
			{ name: "Allocations", note: "Every Material Planning drawing from this sheet, how many pieces each took, and whether it has physically moved yet." },
		],
		calcs: [
			{
				title: "Why the piece count is yours to enter, not calculated from weight",
				item: "Plate 5mm", group: "Plates",
				length: 1800, sec_qty: 2, unit_weight: 7.85,
				formula:
					"A 1800 × 6300 × 5 plate weighs 445.095 Kg. A 1800 × 3000 piece weighs 211.95 Kg. " +
					"Divide one by the other and you get 2.1",
				result: "but the plate yields 2 pieces, plus a 1800 × 300 remnant",
				note:
					"Steel is cut, not poured. Weight says 2.1 pieces fit; geometry says 2. If the system " +
					"took the weight figure it would over-issue on every single plate, and the shortfall " +
					"would only show up when someone went to the rack. So the count is entered by hand, " +
					"with the geometric answer offered as a starting point.",
			},
			{
				title: "One plate, two jobs, sized two different ways",
				item: "Plate 5mm", group: "Plates",
				length: 500, sec_qty: 4, unit_weight: 7.85,
				formula:
					"W1 is 500 × 250 × 5 = 4.90625 Kg per piece, 10 pieces on the sheet. " +
					"Job A needs 18 Kg and ticks Reserve stock without dimensions: 18 ÷ 4.90625. " +
					"Job B unticks it and types 4 pieces: 4 × 4.90625",
				result: "Job A — 18.000 Kg (3.669 Nos)   ·   Job B — 19.625 Kg (4 Nos, 1.625 Kg excess)",
				note:
					"Both are correct, they just answer different questions. Job A reserves exactly what " +
					"the drawing needs and accepts a fractional share of a piece. Job B takes whole pieces " +
					"because that is what the saw will actually produce, and the 1.625 Kg over the " +
					"requirement is excess. Between them they have taken 7.669 of the 10 pieces, and the " +
					"sheet shows 2.331 still free for anyone else.",
			},
		],
		examples: [
			{
				type: "do",
				label: "Let the batch decide",
				text: "You never tick Cut Sheet on a Material Mapping row. Pick the batch, and if a Cut Sheet exists the tick appears with the sheet's name and its free-piece count, and the row takes on W1's dimensions.",
			},
			{
				type: "dont",
				label: "Don't expect the plate's dimensions on the row",
				text: "A cut row shows the PIECE — 500 × 250, not the 2000 × 1000 plate. If you see the plate's size there, the row has not picked up its Cut Sheet; re-select the batch.",
			},
			{
				type: "dont",
				label: "Don't delete a sheet other jobs are drawing from",
				text: "It refuses, and names the Material Plannings holding pieces. Release those allocations first — otherwise their rows would be left reserving pieces of a plan that no longer exists.",
			},
		],
		notes: [
			"W2 goes onto the batch at the FIRST transfer, not the last. From the moment anyone cuts a piece out, the plate in the rack IS the remnant — whether or not the other jobs have collected their pieces yet. Those pieces are still theirs; the Cut Sheet tracks them independently of the batch's size. Cancel that transfer and the batch goes back to its uncut size.",
			"The batch keeps its original NAME throughout, and that name still spells out the original dimensions. Only the batch's Length/Width/Sec Nos are rewritten. This is known and accepted for now.",
			"Nothing here is physical. There is no stock behind W1: the batch still holds its own Kg, and the real movement is the ordinary Material Issue Plan transfer — it simply carries W1's dimensions instead of the plate's. The Cut Sheet owns the arithmetic and the bookkeeping of who has claimed what.",
			"If W1 × count + W2 does not add up to the plate you get a warning naming the row — never a block, since some loss to the saw is normal. The allowance is Cut Sheet Tolerance (%) in Manufyxinvenza Settings, 2% by default; set it to 0 to be told about any difference at all.",
			"Reducing W1 Sec Nos below what jobs have already taken is refused, naming how many are spoken for. Release an allocation first.",
		],
	},
	{
		id: "excess-material-mapping",
		title: "Excess Material Mapping",
		kicker: "Reusing leftovers from other jobs",
		purpose:
			"Instead of buying fresh raw material, this lets you reuse material that's already " +
			"“spare” from a DIFFERENT job — either genuinely sitting back in your own warehouse " +
			"as an off-cut, or simply promised from another job's Excess Material Items table " +
			"before it's even physically moved anywhere. Opened from the “Excess Material " +
			"Mapping” button on any Material Mapping row, or via “Select Item” once you tick " +
			"Excess Material on a batch-less row.",
		fields: [
			{ name: "Item Code / Item Name", note: "The excess item on offer." },
			{ name: "Source", note: "“Returned Batch” (physically back in your own warehouse) or “Not Yet Returned (Pending)” (still just a row in another job's Excess Material Items table)." },
			{ name: "Batch / MIP", note: "The batch number for a Returned Batch, or the source Material Issue Plan for a Not Yet Returned row." },
			{ name: "L (mm) / W (mm) / T (mm)", note: "Dimensions of the excess piece." },
			{ name: "Sec Qty", note: "How many pieces / what quantity is on offer." },
			{ name: "Free/Qty (Kg)", note: "For a Returned Batch, how much of it is still free to claim. For a Not Yet Returned row, the full quantity on offer." },
			{ name: "Supplier", note: "Shown for Not Yet Returned rows, so you know where the material is physically sitting." },
		],
		calcs: [
			{
				title: "Case 1 — Returned Batch (partial claim allowed)",
				item: "ISA100 off-cut", group: "Structurals",
				length: 300, sec_qty: 1, unit_weight: 14.9,
				formula:
					"Batch ISA100-L300-SR054 has 2 pieces free (8.94 Kg total). You only need 1, so you edit Sec Qty down to 1. " +
					"Kg claimed = (300÷1000) × 14.9 × 1",
				result: "4.47",
				note: "The other piece (4.47 Kg) stays free on that same batch for someone else to claim later — same “only the selected quantity” rule as a normal reservation.",
			},
			{
				title: "Case 2 — Not Yet Returned (claim as many pieces as you need)",
				item: "ZZTEST-VIRTUAL-EXCESS", group: "Structurals",
				length: 1000, sec_qty: 6, unit_weight: 5,
				formula: "A 6-piece off-cut at (1000÷1000) × 5 = 5 Kg each. Take 2 for this job: 2 × 5. " +
					"Another job takes 3, and 1 stays free",
				result: "10.0 Kg claimed · 5.0 Kg still free for anyone else",
				note: "Shared out in pieces, exactly like a Cut Sheet. The picker shows Planned Sec Nos beside Free Sec Nos, and an off-cut disappears from it once nothing is left. No Stock Entry is created by claiming: the Material Mapping row's Batch stays blank and its Status reads “Excess Mapped (At Supplier)” or “Excess Mapped (Pending Return)”. When the off-cut physically returns, the new batch attaches itself to EVERY row holding a piece.",
			},
		],
		examples: [
			{
				type: "do",
				label: "Returned Batch — partially reservable",
				text: "A “Returned Batch” row's Sec Qty field is editable, defaulting to the smaller of the batch's own Sec Qty or its free quantity. You can take less than what's on offer, exactly like a normal batch reservation.",
			},
			{
				type: "do",
				label: "Take only what you need",
				text: "Sec Qty in the picker defaults to everything still free, but it is yours to edit. Whatever you leave stays free for another job — the Availability figures on the Excess Material Items row show Allocated and Available in both Sec Nos and Kg, the same way a Cut Sheet does.",
			},
			{
				type: "do",
				label: "A claim turns real by itself when the off-cut comes back",
				text: "Worked example. Job A ends with a 2000mm ISA100 off-cut (20 Kg) still at the supplier, entered in its Excess Material Items table. Job B claims it — Job B's row shows Status “Excess Mapped (Pending Return)”, Batch blank, but Reserved ticked. Weeks later Job A actually walks the material back: its “Return Excess Entry” button creates the return as normal, and the moment that Stock Entry is submitted the new batch (ZZ-L2000-SR014) writes itself into Job B's row, Status flips to “Excess Mapped”, and a green message says so. Nobody re-picks anything, and the material is never free for a third job to grab in between.",
			},
			{
				type: "dont",
				label: "Don't try to change the size of an off-cut someone has claimed",
				text: "Once Job B has claimed it, the off-cut's Length/Width/Sec Qty/Kg are frozen — in the Excess Material Items grid and in the Return Excess Entry dialog alike. Both refuse with the same message naming Job B's Material Planning. This is deliberate: Job B reserved a 2000mm piece, and quietly shrinking it to 1800mm would leave Job B planning around material that no longer exists in that shape.",
			},
			{
				type: "do",
				label: "The measurement was wrong — use Unlink Claim",
				text: "Continuing the example: the off-cut actually measures 1800mm, not 2000mm. Press <b>Unlink Claim</b> on that Excess Material Items row. Job B's reservation is dropped, the off-cut returns to this picker, and the dimensions unlock. Correct them in the Excess Material Items grid itself (1.8m × 10 kg/m = 18 Kg), then claim it again. Note the risk the confirmation warns you about: while unlinked, any other job can claim it first.",
			},
		],
		notes: [
			"“Pending Return” material is excess that hasn't been walked back to stock yet, but eventually will be — claiming it now doesn't stop that from happening later; it just reserves the outcome in advance. If a job has already written its off-cut off as Process Loss, it is gone from stock and no other job can take it. And while any job is still claiming it, the write-off is refused — so it cannot vanish from under you.",
			"Where these rows go at transfer time. A claimed off-cut still at the supplier has no batch in your source warehouse, so it can never appear in the transfer popup's list — there is physically nothing to move, and it is already sitting where the transfer would have sent it. Rather than leaving a silent gap, the popup shows a blue panel: “N item(s) are already at <supplier warehouse> — no transfer needed”, listing each one. It is information, not a problem: it never blocks the rest of the transfer.",
			"<b>Edit dimensions in the Excess Material Items grid.</b> It is the one place an off-cut is described. Raw-material rows used to carry their own Excess Length/Width/Sec Qty that this table was recalculated from on every save — two places for one measurement, where typing in the grid got silently overwritten. Those fields are gone, and the grid is now the only end there is.",
			"<b>Enter Weight, Not Pieces.</b> A tick on the row for when the weight is the figure you have rather than the shape and the count. Off, you type the Length/Width and Sec Nos and the weight follows. On, you type the weight and the Sec Nos is worked back out of it — left fractional on purpose, since 18 Kg of a 4.906 Kg piece is 3.669 of one, and rounding up would claim a piece that is not coming back. Offered only for Structurals and Plates, because only they have a shape to measure.",
		],
	},
	{
		id: "unavailable-items",
		title: "Unavailable Items",
		kicker: "Table 4 of 7 — internal staging",
		purpose:
			"Anything with genuinely no usable stock at all. This table is mostly working " +
			"machinery now, not something you need to act on directly — it's collapsed by " +
			"default to keep the form clean. Every row here is automatically grouped, by item " +
			"code, into the Consolidate Item table below, which is the one you actually work " +
			"from for purchasing.",
		fields: [
			{ name: "Item Code / DUNO / Cust Drawing No", note: "The original per-drawing requirement — kept here for traceability even after it's grouped into Consolidate Item." },
			{ name: "Alternate Item section", note: "An optional per-row substitute, with its own Length/Width/Thickness/Sec Qty/Unit Weight — the older, per-drawing version of the substitution idea now more commonly done once, in bulk, on Consolidate Item instead." },
		],
		notes: [
			"Why it's still here at all: once a Purchase Receipt for these items arrives, the system needs to know exactly which drawing(s) to allocate the received stock back into — that's tracked at THIS row's level, even when the purchase itself was created from the consolidated view above it.",
		],
	},
	{
		id: "consolidate-item",
		title: "Consolidate Item",
		kicker: "Table 5 of 7 — the purchasing table",
		purpose:
			"One row per item code, combining every drawing's need for that item into a single " +
			"purchase-friendly line. If five different drawings all need some ISA100, you get " +
			"ONE row here instead of five — this is the table you actually buy from.",
		fields: [
			{ name: "Required Kg", note: "The total across every drawing/Unavailable Item row that fed into this line." },
			{ name: "Unit Weight", note: "The original item's weight-per-metre (or per Nos), from the Item master — read-only, shown purely for reference so you can see what the Purchase Kg formula is using." },
			{ name: "Length / Width / Thickness / Sec Qty", note: "Enter the size and piece count you intend to buy — Purchase Kg calculates automatically from these." },
			{ name: "Purchase Kg", note: "Auto-calculated, same formula as everywhere else — the Alternate Item's Unit Weight is used instead of the original's, whenever an Alternate Item is set." },
			{ name: "Difference (Purchase Kg − Required Kg)", note: "Almost always a small positive surplus, because you can usually only buy whole pieces/standard lengths, not the exact fractional Kg required. This is normal purchasing rounding, NOT excess material to be returned." },
			{ name: "Alternate Item section", note: "Set once for the whole consolidated line to substitute a different item for every drawing it represents — once set, Length/Width/Thickness/Sec Qty above describe the ALTERNATE item, not the original." },
			{ name: "Purchase size check (on save)", note: "When you change a line's Item, Alternate Item, Length, Width or Thickness, that line is compared against the biggest piece it has to produce, and anything too short or the wrong thickness is listed in an information popup — see the second worked example below. It never blocks the save. Only lines you actually changed are checked, and only when <b>you</b> are the one saving: it used to re-state every undersized line on every save, so editing a batch in a different table raised a popup about a purchase size nobody had gone near — and submitting a Purchase Receipt, which saves the plan behind the scenes to allocate its stock, raised it on the receipt's own screen." },
		],
		calcs: [
			{
				title: "Purchase Kg vs Required Kg",
				item: "ISMB400", group: "Structurals",
				length: 12000, sec_qty: 32, unit_weight: 61.6,
				formula: "You'll buy 32 whole 12m bars. Purchase Kg = (12000÷1000) × 61.6 × 32",
				result: "23,654.40",
				note: "Required Kg across every drawing was 23,039.40 — so Difference = 23,654.40 − 23,039.40 = 614.998 Kg of purchasing surplus, purely from rounding up to whole bars.",
			},
			{
				title: "Buying SHORTER than the longest piece — the size warning",
				item: "ISMB400", group: "Structurals",
				length: 4000, sec_qty: 50, unit_weight: 61.6,
				formula:
					"You enter Length 4000 and Sec Qty 50. Purchase Kg = (4000÷1000) × 61.6 × 50 = 12,320 Kg, " +
					"which comfortably covers the 11,519.701 Kg required — so on WEIGHT alone this looks fine. " +
					"But the longest single ISMB400 piece the drawings need is 6936.01 mm",
				result: "12,320 Kg bought — but no 6936 mm piece can ever be cut from a 4000 mm bar",
				note:
					"On save you'll get an information popup: “ISMB400 — Length ≥ 6936.01 mm (now 4000)”. " +
					"It does NOT block the save — buying short stock is sometimes deliberate — it simply makes sure " +
					"the clash is never silent. Enough total weight is not the same as usable material.",
			},
		],
		steps: [
			"Enter Length/Width/Thickness/Sec Qty for how you actually intend to purchase (e.g. one standard 12m bar, however many pieces).",
			"Purchase Kg and Difference calculate automatically.",
			"Click “Create Material Request” to raise the purchase for the selected rows.",
		],
		examples: [
			{
				type: "do",
				label: "Purchasing surplus is normal, not “excess material”",
				text: "Once received, the 614.998 Kg surplus above becomes ordinary free stock of the batch, available to any future job that needs ISMB400. It is NOT sent through the Excess Material Mapping system — that's reserved for material left over after actually CUTTING a job (an off-cut), which needs someone to deliberately flag it. Buying a bit extra up front never triggers that on its own.",
			},
		],
		buttons: [
			{
				name: "Update & Map Exact Matches",
				note:
					"For every row here: if an active Material Request already covers it, the row is left untouched — a purchase is already in motion. Otherwise the row is removed and stock is re-checked against the underlying drawing requirements: an exact match now found goes to Available Raw Materials, a batch item with still no exact match goes to Material Mapping (blank batch, assign by hand), and it only stays unavailable if truly nothing exists.",
			},
			{ name: "Create Material Request", note: "Raises a purchase for the selected rows — orders the Alternate Item instead of the original wherever one is set." },
		],
	},
	{
		id: "weight-summary",
		title: "Weight Summary",
		kicker: "Where the plan stands, in Kg",
		purpose:
			"Four running totals and one difference, all recalculated on every save. Read together " +
			"they answer: how much does this plan need, how much of it is settled, and are we " +
			"about to commit more steel than the job actually calls for?",
		fields: [
			{ name: "Total Weight — Plates & Structurals (Kg)", note: "Everything the plan needs. The sum of required Kg across the whole Raw Materials table — the figure the other three are measured against." },
			{ name: "Weight — Exact Raw Material (Kg)", note: "The part covered by batches that are already the right size. Sum of required Kg in Available Raw Materials (Exact Match)." },
			{ name: "Expected Item Weight — Material Mapping (Kg)", note: "What the Material Mapping rows were SUPPOSED to need — the sum of their required Kg, before any batch was assigned." },
			{ name: "Weight of Cross Item Mapped (Kg)", note: "What the batches actually assigned to those rows WEIGH — the sum of their Calc Qty. Larger than the line above whenever a bigger piece was used to cover a smaller requirement." },
			{ name: "Difference in Kg — Batch Mapped Items", note: "Cross Item Mapped minus Expected. Appears as soon as one row is mapped, and says how many of the rows are mapped so far." },
		],
		notes: [
			"<b>The Difference is the excess you will have to get back.</b> A positive figure means the batches committed weigh more than the requirement they cover — normal when a 6 m bar covers a 4 m need, but it is steel that goes out to the supplier and has to come back. The panel says so explicitly when it is positive.",
			"<b>Green is not automatically good.</b> A large positive difference on a plan about to be transferred means a lot of material will be sitting at the supplier waiting to be returned. It is worth looking at before transferring, not after.",
			"<b>The difference only appears once something is mapped.</b> Before that there is nothing to compare, so the panel stays blank rather than showing a misleading zero.",
			"<b>Exact Match contributes no difference.</b> Those batches are the right size by definition, which is why only the Material Mapping side is compared.",
		],
		buttons: [
			{ name: "Update SO Difference", note: "Writes this plan's difference back onto the Sales Order for the drawings it covers, so the excess is visible from the order rather than only from here. Save the document first." },
		],
	},
	{
		id: "actions",
		title: "Status and Validate Stock",
		kicker: "The top-bar actions",
		purpose:
			"What the buttons along the top of a Material Planning do, and when each one is the " +
			"right thing to press.",
		steps: [
			"<b>Check Mapping</b> — reports everything wrong with the mapping: batches assigned in both tables, more reserved across all plans than the batch holds, allocated Nos beyond what the batch has, anything still in Unavailable Items. It sets nothing; the status looks after itself.",
			"<b>Validate Stock</b> — a read-only check. For every item and batch the plan has committed, it shows the Kg and Sec Nos claimed against what the batch actually holds. Changes nothing.",
		],
		fields: [
			{ name: "Status — Open", note: "Nothing mapped and nothing outstanding." },
			{ name: "Status — Working", note: "Something is mapped, but not all of it is reserved — or something is still sitting in Unavailable Items. The normal working state." },
			{ name: "Status — Batch Mapping Completed", note: "Every mapped row is reserved and nothing is left unavailable. Read-only and recalculated on every save: you never set it, and it cannot be wrong." },
		],
		notes: [
			"<b>Validate Stock before transferring, every time.</b> It is the one place that shows a fractional Sec Nos total — which means several drawings are sharing one bar or sheet, and someone has to decide at transfer time whether to hand over the lower or the higher whole piece count. Better known now than in front of the storeman.",
			"<b>The status follows the reservations, in both directions.</b> Reserve the last row and it reads Batch Mapping Completed; unreserve one and it goes back to Working by itself. There is nothing to press and nothing to reopen. It used to be a one-way ratchet — marked complete by hand and never moved again — so a plan could sit reading <i>Batch Mapping Completed</i> with not one row reserved, and a Material Issue Plan only ever offers reserved rows for transfer. It said it was ready and would have moved nothing.",
			"<b>There is no Create → Production Plan button any more.</b> The Production Plan is raised by hand and picks its own drawings — which is the point: taking every BOM on this plan was rarely what was wanted. This plan is still what the Production Plan's drawing picker reads from, so nothing about the order of work changes.",
			"<b>A Production Plan does not lock this plan.</b> You can still map and reserve after one exists — but anything you change afterwards will not be reflected in it unless it is refreshed.",
		],
		buttons: [
			{ name: "Check Mapping", note: "Lists what is wrong with the mapping. Changes nothing — the status is worked out from the reservations on every save." },
			{ name: "Validate Stock", note: "Shows planned Kg and Sec Nos per item and batch against what is really in the warehouse. Read-only." },
		],
	},
	{
		id: "after-purchase",
		title: "After Purchase: Automatic Allocation",
		kicker: "Table 6 of 7 — what happens on receipt",
		kind: "info",
		purpose:
			"Once a Purchase Receipt for a Material Request created from this plan is submitted, " +
			"allocation happens AUTOMATICALLY — there is no button to click for this part.",
		steps: [
			"The original item was purchased (no substitution) → the received batch lands in Available Raw Materials, exactly like a real exact match.",
			"A consolidated purchase, or an Alternate Item, was received → the batch lands in Material Mapping instead of Exact Match, with “Reserve stock without dimensions” already switched on for you. Sec Nos comes through as an exact fraction of the purchased piece size — settle it into whole pieces at transfer time.",
			"If the purchase was consolidated across several drawings' worth of the same item, the received quantity is split sequentially — the first drawing (by row order) is filled completely, then the next, and so on. Any purchasing surplus left after every drawing is fully covered simply becomes free warehouse stock (see the Consolidate Item section above) — it isn't assigned to any one drawing.",
		],
	},
];

// ─── Production Plan — the old manual's single "production-plan" section split
// three ways, following the client's own reference nav (Drawing table / Operation
// table as siblings). "Drawing / Item Table" is new content, written from the
// po_items fields this session has used directly and repeatedly building test
// Production Plans (item_code, bom_no, planned_qty, stock_uom, custom_drawing,
// custom_duno_mark_no, custom_customer_drawing_number, sales_order,
// custom_material_planning, custom_customer_weight_kg) -- not fabricated, but also
// not yet reviewed against the live form the way the rest of this page has been. ─
const ERP_MANUAL_PRODUCTION_PLAN_CHILDREN = [
	{
		id: "type-setup",
		title: "Type & Setup",
		kicker: "Before the tables — what kind of job this is",
		purpose:
			"Production Plan is where a job actually gets scheduled, once Material Planning has " +
			"sorted out where every raw material is coming from. Type decides the naming series " +
			"and, downstream, which warehouse defaults are pulled onto the Material Issue Plan.",
		fields: [
			{ name: "Type (Internal Job / Supplier Job / Supplier with Material)", note: "Drives the naming series. Doesn't restrict which Work Type each individual operation uses on the Operation table below — those can still be mixed within one plan." },
		],
		buttons: [
			{ name: "Job work order & MIP", note: "Appears once the Production Plan is submitted. Creates the Job work order AND its Material Issue Plan together in one click. Safe to click again later — it just opens what already exists instead of duplicating." },
			{ name: "Delete Job work order and MIP", note: "Sits next to the Vendor/Contractor field. Deletes both together, with a confirmation prompt — refuses outright if any real stock movement or production has already happened against either one, so nothing gets silently lost." },
		],
		notes: [
			"If any operation in the Operation table has Work Type Subcontractor, Vendor/Contractor must be set before “Job work order & MIP” will create anything.",
		],
	},
	{
		id: "drawing-table",
		title: "Drawing / Item Table",
		kicker: "Which drawings this plan produces",
		purpose:
			"One row per drawing/item this Production Plan is scheduling. Each row carries its " +
			"own Sales Order, DUNO/Mark No and Customer Drawing Number, and points back at the " +
			"Material Planning that reserved its raw material — that link is how Material Issue " +
			"Plan later knows exactly which reserved rows belong to this job.",
		fields: [
			{ name: "Item Code / BOM No", note: "What is being produced, and the Bill of Materials it is produced against." },
			{ name: "Planned Qty / Stock UOM", note: "How many of this item this plan produces." },
			{ name: "Sales Order / DUNO Mark No / Customer Drawing Number", note: "Traceability back to the customer order and the specific drawing/mark." },
			{ name: "Material Planning", note: "The Material Planning document that reserved raw material for this row. Material Issue Plan reads this link to pull in only the rows belonging to this plan's own drawings." },
			{ name: "Customer Weight (Kg)", note: "The customer-provided weight for this item, carried through from the Sales Order/Drawing." },
		],
	},
	{
		id: "operation-table",
		title: "Operation Table (Process Planning)",
		kicker: "The sequence of operations, and who performs each one",
		purpose:
			"The ordered list of operations this job goes through — e.g. Fit-up, Welding, Final, " +
			"Blasting, Painting. One Supplier Operation Entry gets created per row, in this exact " +
			"order, once the Job work order is created.",
		fields: [
			{ name: "Operation Name", note: "The step itself." },
			{ name: "Work Type (Internal Jobcard / Subcontractor)", note: "Who performs THIS operation. Can vary row by row in the same plan — e.g. Welding done in-house, Blasting sent to a supplier — but every Subcontractor row must come before every Internal Jobcard row, no interleaving." },
			{ name: "Inspection Mandatory", note: "Tick on any operation that needs a formal QC sign-off before its completed quantity counts. Covered in full in the Inspection category." },
		],
		buttons: [
			{ name: "Set Work Type", note: "Bulk-sets Work Type across selected rows instead of editing each one by hand." },
		],
	},
];

const ERP_MANUAL_JOB_WORK_ORDER_CHILDREN = [
	{
		id: "overview",
		title: "Job work order",
		kicker: "One document drives every operation",
		purpose:
			"Created from a submitted Production Plan, the Job work order is the single execution " +
			"document for EVERY operation in the plan, whether it's done in-house or by a supplier — " +
			"there is no separate Work Order/Job Card involved.",
		fields: [
			{ name: "Drawing Items", note: "Every drawing/DUNO this job covers, each with its own Customer Provided Weight, Planned RM Weight, Mapped Weight, Excess Weight, and Transferred Weight — rolled up from Material Planning." },
			{ name: "All Operations Complete", note: "Ticks itself once every operation in the chain has been submitted. Informational — it no longer gates anything: <b>Make Final Stock Entry</b> follows the last operation's completed pieces instead, so part of a job can be booked without waiting for the whole of it." },
			{ name: "Status", note: "<b>Open → Working → Completed</b>, and it moves on its own. Open on submit; Working the moment any operation has quantity logged against it; Completed once every operation is submitted <i>and</i> the Material Issue Plan's Final Stock Entry has been submitted. It is worked out fresh each time rather than remembered, so cancelling that Final Stock Entry puts the order back to Working." },
		],
		steps: [
			"Submitting the Job work order and clicking “Job work order & MIP” back on Production Plan creates one Supplier Operation Entry per Operation table row, in sequence order.",
			"Each operation only becomes submittable once every earlier one already is — operation 3 can't be completed before operation 2 is.",
			"The Operations tab shows a live summary table — Seq, Operation, Status, Overall Qty, Available to Consume, Total Consumed, Difference, Entry, Drawings. Click any operation's name (shown in blue, underlined) to jump straight into that Supplier Operation Entry.",
		],
		buttons: [
			{ name: "Open MIP", note: "Opens this job's Material Issue Plan. Sits on its own, before the Create group, because it goes to a document that already exists rather than making a new one. It only appears once there is an MIP to open. The Material Issue Plan carries the matching <b>Open Job Work Order</b> button back the other way." },
			{ name: "Material Issue Plan (under Create)", note: "Creates the Material Issue Plan if it doesn't already exist, or opens the existing one." },
			{ name: "Supplier Operation Entries (under Create)", note: "Creates any still-missing Supplier Operation Entry in the chain — normally already done automatically by “Job work order & MIP”." },
		],
		notes: [
			"“Job work order” is a display name only — underneath, it's still the same Subcontracting Order doctype; it just reads as “Job work order” everywhere in the UI.",
			"The old separate “Work Order / Subcontract PO” create option under Production Plan is disabled — use “Job work order & MIP” there instead.",
			"Standard ERPNext offers <b>Subcontracting Receipt</b> under Create on a submitted order. It is removed here: a job work order raised from a Production Plan has no service items and no Raw Materials Supplied table to receive against, so that button could only produce a broken receipt. Finished goods come in through the Material Issue Plan's Final Stock Entry instead.",
			"Cancelling the job work order cancels and removes every Supplier Operation Entry under it, in reverse sequence. That is the only supported way to undo an operation — see Supplier Operation Entry.",
		],
	},
];

const ERP_MANUAL_SOE_CHILDREN = [
	{
		id: "overview",
		title: "Supplier Operation Entry (Operations)",
		kicker: "One per operation, tracking Nos completed",
		purpose:
			"One Supplier Operation Entry exists per Operation table row. The first operation " +
			"tracks Kg consumed from what was transferred; every operation after that tracks Nos " +
			"(pieces) handed forward from the one before it.",
		fields: [
			{ name: "Consumption Log", note: "Log how many Nos (pieces) of each drawing were completed, with a Date. Weight (Kg) is auto-calculated from the drawing's own per-piece weight." },
			{ name: "Drawing Details", note: "Per-drawing Qty to Manufacture, Available to Consume (Nos), Completed Qty (Nos), Customer Weight (Kg) and Planned Weight (Kg)." },
			{ name: "Available to Consume (Nos)", note: "The first operation gets this from what's actually been transferred; every later one gets it from the PREVIOUS operation's own Completed Qty, once that operation is saved (while still draft) or submitted. On the Job Work Order's <b>Operations</b> tab this reads as what is <i>still left</i> to consume, with what arrived shown beside it — <i>0.000 of 8.000</i> — so a finished operation stops offering its full quantity. A red figure means the operation completed more pieces than it was handed." },
		],
		steps: [
			"Logging Nos against a drawing in Consumption Log auto-advances Status from Open to In Progress, and — when Inspection Mandatory is off — immediately updates that drawing's Completed Qty.",
			"Status must be set to Completed before a Supplier Operation Entry can be submitted, and every earlier operation in the sequence must already be submitted too.",
			"Completed is only accepted when the operation really is finished: every drawing must have reached the quantity this operation was given — its own Qty to Manufacture on operation 1, whatever the previous operation handed over from operation 2 on. A drawing that received nothing from the operation before it blocks Completed too, because there is nothing there to have finished.",
			"Setting Status to Completed asks “Mark this operation Completed and submit it?” — answering Yes saves and submits in one step, so there is no separate Submit click. Answering No puts the Status back where it was.",
		],
		buttons: [
			{ name: "Add All Drawing (Testing group)", note: "Fills Consumption Log with one row per drawing at its full available quantity in one click, instead of adding rows one by one. For quick testing or data entry, not a normal production step — which is why it only appears when <b>Auto Purchase from Material Planning</b> is ticked in Manufyxinvenza Settings, the same switch that reveals the Auto Purchase section on Material Planning. Leave that off on a live site and this button is not there at all." },
		],
		notes: [
			"If Inspection Mandatory is ticked for this operation, Consumption Log no longer completes anything directly — see Inspection for what happens instead. On such an operation Completed also needs the inspection <i>cleared</i>: no round may still be Pending, and since the quantity comes from Accepted Qty, an operation cannot be closed on pieces QC has not passed.",
			"<b>A Supplier Operation Entry cannot be cancelled on its own.</b> The Job work order's Operations tab, the next operation's Available to Consume and the Drawing Items' completion all report from submitted entries, so a cancelled one leaves the order quoting a quantity nothing accounts for. To undo an operation, cancel the Job work order — that takes the whole chain together and leaves nothing pointing at a cancelled document.",
			"Amending an entry that was cancelled before this rule existed works normally, and the amendment starts at Open rather than Completed: the cancelled document's Status copies across but its finished quantities do not, so re-enter the Consumption Log before completing it again.",
		],
	},
];

const ERP_MANUAL_INSPECTION_CHILDREN = [
	{
		id: "overview",
		title: "Inspection (Mandatory Operations)",
		kicker: "QC sign-off before quantity counts as done",
		purpose:
			"When an operation's Inspection Mandatory box is ticked, logging Nos in Consumption " +
			"Log no longer completes them on its own — they sit as pending review until an " +
			"Inspection Entry accepts them. This is the one gate that guarantees nothing moves to " +
			"the next operation, or into a Final Stock Entry, without QC sign-off.",
		fields: [
			{ name: "Inspection Items (on the Supplier Operation Entry)", note: "One row per drawing, auto-showing what's been logged in Consumption Log but not yet accepted. Recalculates itself on every save — nothing to maintain by hand, and it never shows more than the drawing's real Qty to Manufacture, however many times something is re-logged." },
			{ name: "Inspection Entry — Status / Feedback / Overall Remarks / Rework Remarks", note: "Status is Open/Working/Completed; Feedback is Ok/Not Ok." },
			{ name: "Inspection Items (on the Inspection Entry)", note: "One row per drawing, copied in from the source Supplier Operation Entry: Completed Qty (frozen at creation), Accepted Qty (you enter), Rejected Qty (auto = Completed − Accepted)." },
		],
		steps: [
			"Click “Create Inspection” on the Supplier Operation Entry's Inspection tab — it logs the call and creates the Inspection Entry in one step, carrying over whatever is currently pending.",
			"Enter Accepted Qty per drawing row — Rejected Qty fills in automatically.",
			"Set Feedback before marking Status Completed — trying to complete without it first shows “Enter Feedback to complete it” and reverts Status.",
			"Set Status to Completed and save — you're asked to confirm (“cannot be edited once submitted”); confirming saves AND submits in one action, there is no separate manual Submit step.",
			"On submit, each row's Accepted Qty is added onto that drawing's Completed Qty on the Supplier Operation Entry — this is what lets the next operation proceed. Rejected Qty isn't written anywhere; it simply reappears in the Supplier Operation Entry's own Inspection Items table the moment it's logged again in Consumption Log, ready for another round.",
		],
		calcs: [
			{
				title: "A full rework round-trip",
				item: "Drawing 1", group: "Qty to Manufacture: 2 pieces",
				sec_qty: "see steps", unit_weight: "n/a",
				formula:
					"Round 1: 2 Nos logged in Consumption Log → 2 pending in Inspection Items → Inspection Entry 1: Accepted 1, Rejected 1 → " +
					"Completed Qty becomes 1, and 1 stays pending (capped at the real 2-piece total no matter how many times it's re-logged). " +
					"Round 2: the rejected piece is reworked and logged again → 1 pending again → Inspection Entry 2: Accepted 1",
				result: "2 / 2 (fully complete)",
				note: "Completed Qty finishes at exactly 2 — the drawing's real total — never more, regardless of how many rounds or re-logged Nos it took to get there.",
			},
		],
		examples: [
			{
				type: "do",
				label: "Rejected Nos are never lost",
				text: "Re-logging the same drawing in Consumption Log after a rejection brings it straight back into the Inspection Items table for another round — with no validation blocking the resubmission, even though the cumulative log total now exceeds the drawing's nominal quantity.",
			},
			{
				type: "dont",
				label: "Don't expect Consumption Log alone to complete anything once Inspection Mandatory is on",
				text: "Completion only ever happens through a submitted Inspection Entry's Accepted Qty — logging Nos just queues them for review.",
			},
		],
		notes: [
			"Rework Remarks is mandatory whenever total Rejected Qty across the Inspection Entry's rows is greater than 1.",
			"Total Checked / Cleared / Rework Qty still appear (read-only) at the top of the Inspection Entry for reporting — they're auto-totalled from the Inspection Items rows, not entered directly.",
		],
	},
	{
		id: "insp-calls",
		title: "Inspection Calls and Rounds",
		kicker: "How QC gets asked, and how retries are counted",
		purpose:
			"Inspection is a conversation between two teams, and the Inspection Call Log is the " +
			"record of it. Manufacturing or Purchasing logs a call to say material is ready to be " +
			"looked at; QC records the result on a separate Inspection Entry. One round is one " +
			"call and its answer, and a rejection simply starts another round.",
		fields: [
			{ name: "Round No", note: "Numbered from 1 upward. Filled in automatically if left blank, so rounds stay in order however they were entered." },
			{ name: "Inspection Call Date", note: "When QC is being asked to attend." },
			{ name: "Round Status (Pending / Completed)", note: "Pending until this round's Inspection Entry is submitted." },
			{ name: "Inspection Entry", note: "Link to the entry that answered this round. Blank while the round is still pending." },
			{ name: "Rework Remarks", note: "What came back from that round." },
			{ name: "Inspection Status (on the source document)", note: "Open / Working / Completed. On submit of an Inspection Entry, the source document's Inspection Status is set to whatever status the inspector chose — it mirrors the inspector's own judgement rather than being re-derived from the accepted and rejected numbers." },
		],
		steps: [
			"<b>Create Inspection</b> on the source document logs a new call round.",
			"Creating an Inspection Entry picks up the most recent round that is still Pending and has no entry against it, and links itself back onto that round. If no such round exists, you are told to log a call first.",
			"The inspector fills in the result, sets Status to Completed, and submits — which closes that round and mirrors the status back onto the source document.",
			"A rejection needs no special handling: log another call, and round 2 begins.",
		],
		notes: [
			"The two gates are deliberately different. A <b>Supplier Operation Entry</b> only needs at least one inspection call logged before it can be submitted — the intent is that QC has been engaged, not that sign-off is complete. A <b>Purchase Receipt</b> is stricter and will not submit until its Inspection Status actually reads Completed.",
			"Round counts and rework attempts are what the <b>Inspection Status Report</b> reports on — see Reports.",
		],
	},
	{
		id: "insp-purchase-receipt",
		title: "Incoming Goods Inspection",
		kicker: "Inspecting what a supplier delivered",
		purpose:
			"The same Inspection Entry document also inspects incoming material on a Purchase " +
			"Receipt. Where an operation inspection asks “are these finished pieces acceptable”, " +
			"this one asks it of each delivered line — and the receipt cannot be submitted until " +
			"it has an answer.",
		fields: [
			{ name: "Inspection Required (on the Item)", note: "This is the switch. Incoming inspection applies to a Purchase Receipt only when at least one item on it has Inspection Required ticked on its Item master — it is opt-in per item, not per receipt." },
			{ name: "Inspection Items (on the Inspection Entry)", note: "One row per inspection-required line on the receipt, with its item code, received Qty and a link back to the exact receipt row. Lines whose item does not require inspection are not included at all." },
			{ name: "Accepted Qty / Rejected Qty", note: "Entered per line. This is a per-row result, not one verdict for the whole delivery, so a receipt can be part-accepted line by line." },
			{ name: "Inspection Accepted Qty / Rejected Qty / Remarks (on the receipt row)", note: "Read-only. Written back onto the Purchase Receipt's own rows when the Inspection Entry is submitted, so the result stays visible on the receipt itself." },
		],
		steps: [
			"On the Purchase Receipt, click <b>Create Inspection</b> and set the call date. The receipt is still in draft at this point — that is the intended order.",
			"Create the Inspection Entry from the logged call. It arrives prefilled with one row per inspection-required line.",
			"Record Accepted Qty and Rejected Qty per line, add remarks, set Status to Completed and submit.",
			"The results are written back onto the receipt rows, and the receipt's Inspection Status becomes Completed.",
			"Submit the Purchase Receipt. Batches are created at that point, not before — so nothing enters stock ahead of its QC result.",
		],
		notes: [
			"Rejected material goes to the row's <b>Rejected Storage Location</b>, kept apart from accepted stock.",
			"Any QC remark recorded against the receipt is carried onto the batch as <b>Batch Remarks</b>, so it stays with the physical piece rather than only on the paperwork.",
			"A receipt where no item requires inspection has no gate at all and submits normally.",
		],
	},
];

// ─── Material Issue Plan — migrated verbatim from the old Material Issue Plan
// manual, one child per topic exactly as that page's sidebar listed them. ───────
const ERP_MANUAL_MATERIAL_ISSUE_PLAN_CHILDREN = [
	{
		id: "overview",
		kind: "overview",
		flow: false,
		kicker: "Start here",
		title: "What a Material Issue Plan Is For",
		purpose:
			"One Material Issue Plan per Production Plan. It pulls in every raw-material row " +
			"reserved for that job's drawings, and is the only place stock actually moves: out " +
			"to the supplier (or your WIP warehouse), optionally via CNC, and back again as " +
			"excess. Nothing here invents quantities — it inherits what Material Planning " +
			"reserved and asks you to decide the one thing a planner cannot know in advance: " +
			"how many whole physical pieces are going out today.",
		buttons: [
			{ name: "Open Job Work Order", note: "Opens the job work order this plan belongs to. The two documents are worked on together, so each opens the other in one click — the job work order carries the matching <b>Open MIP</b> button. Still available on a Completed plan, where the rest of the form is locked, because opening a document is not an edit." },
		],
	},
	{
		id: "raw-materials",
		title: "Raw Materials",
		kicker: "The list, and where it comes from",
		purpose:
			"Every reserved row for this job's drawings, pulled from the linked Material " +
			"Planning(s). It is rebuilt rather than edited: press <b>Refresh Raw Materials</b> " +
			"and the rows are re-read from Material Planning, which is how a late purchase or a " +
			"batch mapped after this plan was created still finds its way in.",
		fields: [
			{ name: "Reqd Qty", note: "What this row must transfer — the weight of the batch mapped to it in Material Planning. Not the customer's weight and not the drawing's; the actual mapped material." },
			{ name: "Issued Qty", note: "Cumulative Kg transferred so far across every Stock Entry from this plan. A row can be issued in stages." },
			{ name: "Excess Qty", note: "Reqd Qty minus the drawing's own planned raw-material weight — surplus the mapped batch carries beyond what the drawing needs. Set when the row is fetched." },
			{ name: "Transfer Excess Kg", note: "Surplus created by YOU rounding Sec Nos up at transfer time. Separate from Excess Qty, and accumulates across partial transfers." },
			{ name: "Sec Qty / Sec UOM", note: "The row's share in pieces. Frequently fractional — see the worked example below, that is expected and not an error." },
			{ name: "CNC Process", note: "Inherited from Material Planning. Ticked means this material must go to the CNC warehouse first; it is not a preference." },
			{ name: "Batch / Batch Remarks", note: "The reserved batch and any remarks recorded against it at inspection." },
		],
		examples: [
			{
				type: "dont",
				label: "Don't type into these rows expecting it to stick",
				text: "Every row here is rebuilt from Material Planning on the next refresh, so nothing typed on one survives. To change what a row draws from, change it there. The rows used to carry their own editable Excess Return and Cut Sheet fields, which did survive a refresh — both are gone: an off-cut is described once in the Excess Material Items table, and a cut once on its Cut Sheet.",
			},
			{
				type: "do",
				label: "Refresh after a late purchase",
				text: "Stock bought after this plan was created is allocated back into Material Planning by the Purchase Receipt, which refreshes this plan automatically. If you have the form open, reload it.",
			},
		],
		notes: [
			"Only this plan's own drawings appear. One Material Planning can cover ten drawings and feed ten separate Material Issue Plans; each pulls only the rows belonging to the drawings in its own Production Plan.",
			"<b>The Cut Sheet panel on a row is reference only.</b> Where the chosen batch has a Cut Sheet, the row shows its To Use and Balance sizes read-only, taken from that sheet — they are what the transfer's Stock Entry carries, so they are worth having in front of you. The cut itself is decided on the Cut Sheet, and on the Material Planning row that claims pieces from it; nothing on this row changes it.",
			"Rows fulfilled from a Cut Sheet arrive already sized to the PIECE, not the plate — a 2000 × 1000 sheet cut into 500 × 250 pieces shows 500 × 250 here. That is what physically goes out.",
		],
	},
	{
		id: "warehouses",
		title: "Warehouses",
		kicker: "Where material goes",
		purpose: "Four warehouses decide every movement this plan can make. Three are needed before anything can be transferred.",
		fields: [
			{ name: "Source Warehouse", note: "Where the reserved stock is now — normally Stores. Defaults from the Production Plan's Raw Material Warehouse." },
			{ name: "Supplier / WIP Warehouse", note: "The destination. For a supplier job this is the Job Worker's own warehouse, resolved automatically once a Job Worker is set on the Subcontracting Order. For an internal job there is no supplier, so this is entered by hand and is the ONLY place the WIP warehouse is recorded." },
			{ name: "CNC Warehouse", note: "Required if any row is flagged CNC Process. Material goes here first and is forwarded on afterwards." },
			{ name: "Finished Goods Warehouse", note: "Receives both the finished item (Make Final Stock Entry) and returned off-cuts (Return Excess Entry). Neither button works until it is set." },
		],
		notes: [
			"A blank Supplier/WIP Warehouse blocks every transfer and quietly breaks the weight tracking back on the Subcontracting Order — if a transfer button does nothing useful, check here first.",
		],
	},
	{
		id: "transfer",
		title: "Select Materials to Transfer",
		kicker: "The popup that moves stock",
		purpose:
			"One popup for every leg — source to supplier, source to CNC, and CNC onward — so " +
			"there is a single place to learn. It lists what is still pending, lets you take " +
			"part of it, and is the only point in the whole system where a fractional Sec Nos " +
			"becomes whole physical pieces. It carries two tabs: <b>Raw material to transfer</b>, " +
			"which is the transfer itself, and <b>Consolidate item for excess return plan</b>, " +
			"where the off-cut coming back is measured.",
		fields: [
			{ name: "Planned", note: "What this row was always going to transfer." },
			{ name: "Transferred", note: "What has already gone, across earlier partial transfers. Re-open the popup after a partial transfer and this is how you see where you stand." },
			{ name: "In Stock", note: "What the batch physically holds in the source warehouse right now. Zero usually means the Purchase Receipt has not been made yet — the row is planned and reserved, but the steel is not in the building." },
			{ name: "Sec Nos", note: "Editable. The hint below it reads e.g. “7.92 (Plan) · or 8 whole” so you can see the planned fraction and the nearest whole-piece figure together." },
			{ name: "Transfer Qty (Kg)", note: "Read-only, derived from Sec Nos. It is not editable on purpose: a hand-typed weight that disagreed with the piece count would ship a Stock Entry whose Sec Qty and weight contradict each other, and consumption downstream is driven by Sec Qty." },
		],
		steps: [
			"Open <b>Transfer → Select Materials to Transfer</b>. A readiness check runs first and tells you about anything that would silently reduce what moves — stock mapped but not reserved, CNC rows with no CNC warehouse, or material already sitting at the supplier.",
			"Tick the rows to send. Rows short of stock are left unticked for you.",
			"Adjust <b>Sec Nos</b> where you must hand over whole pieces. The system re-checks free stock for the higher figure and refuses it outright if the batch cannot cover it.",
			"Switch to <b>Consolidate item for excess return plan</b> and measure the off-cut, one line per item — for the items that have one. A line whose Excess Kg (system) is zero has its boxes closed: nothing was left over, so there is nothing to measure. Optional — leave it blank and only a rounding surplus is booked, as before.",
			"Submit. The Stock Entry is created, Transferred goes up, and the excess is written to the Excess Material table.",
			"Come back later for the rest. Partial transfers are expected, and the popup shows exactly how much has gone and how much is left.",
			"<b>Save and Close</b> at any point parks everything — the ticks, the Sec Nos, and the measured off-cuts — without transferring or validating anything. Reopen the popup and it is all still there.",
		],
		calcs: [
			{
				title: "Why Sec Nos reads 4.5 and what to do about it",
				item: "ISMB450", group: "Structurals",
				length: 900, sec_qty: "4.5 planned", unit_weight: 72.4,
				formula:
					"One purchased bar is 900 mm, so one piece is (900÷1000) × 72.4 = 65.16 Kg. " +
					"This batch is shared by 5 drawings — 8 Nos in total across the Material Planning — " +
					"but this plan covers only 3 of them, so it pulls 4.5 Nos. " +
					"Leave it: 4.5 × 65.16. Or type 5: 5 × 65.16",
				result: "293.22 Kg (4.5 Nos)   →   or 325.80 Kg (5 Nos), 32.58 Kg excess",
				note:
					"The fraction is not an error — it is this plan's share of a bar the other jobs also " +
					"draw from. Material Planning always reserves the exact weight a drawing needs and " +
					"never rounds, because at planning time nobody knows which jobs will be issued " +
					"together. Type 5 only if you genuinely cannot hand over half a bar; the extra " +
					"32.58 Kg is recorded as excess to come back.",
			},
			{
				title: "Where that 32.58 Kg lands on the item table",
				item: "ISMB450", group: "Structurals",
				length: 900, sec_qty: "3 rows sharing the batch", unit_weight: 72.4,
				formula:
					"Those 4.5 Nos were 3 drawings at 2 Nos, 1.5 Nos and 1 Nos. The surplus belongs to " +
					"all three, split by their Sec Nos: 2÷4.5 × 32.58, 1.5÷4.5 × 32.58, 1÷4.5 × 32.58",
				result: "14.48 + 10.86 + 7.24 = 32.58 Kg",
				note:
					"Each figure lands in that row's Transfer Excess Kg, so the surplus is visible against " +
					"the drawings that caused it rather than as one lump. The parts always add back to the " +
					"whole. Round up again on a later transfer and the column accumulates.",
			},
		],
		examples: [
			{
				type: "do",
				label: "Transfer in stages",
				text: "Send what you have, come back for the rest. The popup nets off what has already gone, so you can never double-issue a row by revisiting it.",
			},
			{
				type: "dont",
				label: "Don't expect a row with no stock to move",
				text: "If In Stock reads 0 the batch is not in the source warehouse yet. The row stays pending, and a red panel explains why rather than leaving you to work it out.",
			},
			{
				type: "dont",
				label: "Don't go looking for material already at the supplier",
				text: "A row fulfilled from an off-cut that never left the supplier is deliberately absent from the list — there is nothing in your warehouse to move. A blue panel names those rows so the gap is explained rather than silent.",
			},
		],
		notes: [
			"Nothing is offered unless it is BOTH purchased and reserved. Reserving is a separate deliberate step back on Material Planning; if stock is mapped but not reserved, the readiness check names the Material Planning so the fix is one click away.",
			"Nothing rounds by itself, anywhere in the system. This popup is the only place a fraction becomes whole pieces, and only because you typed it.",
		],
	},
	{
		id: "excess-plan",
		title: "Consolidate Item for Excess Return Plan",
		kicker: "The transfer popup's second tab",
		purpose:
			"Where the material coming back is measured, at the moment it is being sent out. " +
			"It consolidates whatever is ticked on the first tab <b>by item</b> and carries no " +
			"batch reference at all — an off-cut comes back as one shape however many batches " +
			"it was drawn from, so it is asked for once per item rather than once per batch.",
		fields: [
			{ name: "Item", note: "One line per item, with the number of batch rows behind it shown underneath. Ten rows on the transfer tab commonly become five or six lines here." },
			{ name: "Planned Drawing Wt", note: "What the drawings actually call for, added up across every selected row of that item. Read-only." },
			{ name: "Planned Transfer Wt", note: "What is being sent, added up the same way. Follows the ticks and the Sec Nos on the first tab, so it changes as you edit them." },
			{ name: "Excess Kg (system)", note: "<b>Planned Transfer Wt − Planned Drawing Wt.</b> What the transfer is sending beyond what the job needs. Read-only." },
			{ name: "Length / Width / Sec Qty", note: "The off-cut you expect back. Entered rather than inferred: the system knows the weight of the surplus, never its shape. <b>Closed when Excess Kg (system) is zero or negative</b> — the transfer sent no more than the drawings called for, so there is no off-cut to describe. Width is closed for Structurals in any case; only the Plates formula uses it, and Thickness is always read-only." },
			{ name: "Excess Kg (entered)", note: "Calculated live from those dimensions with the same formula as everywhere else — Length ÷ 1000 × Unit Weight × Sec Qty for Structurals, with Width and Thickness for Plates." },
			{ name: "Difference", note: "<b>Excess Kg (entered) − Excess Kg (system).</b> Green when the two agree, blue when more is coming back than the transfer created, red when part of it is unaccounted for." },
		],
		calcs: [
			{
				title: "The difference, both ways round",
				item: "Any item", group: "Structurals",
				length: "—", sec_qty: "—", unit_weight: "—",
				formula:
					"Drawings call for 100 Kg and 110 Kg is being transferred, so the system figure is " +
					"110 − 100 = 10 Kg. Measure an off-cut of 11 Kg: 11 − 10. Measure 9 Kg instead: 9 − 10",
				result: "+1 Kg (extra)   or   −1 Kg (missing)",
				note:
					"Positive means more is coming back than the transfer created. Negative means part " +
					"of the excess is unaccounted for — usually the off-cut was mis-measured, or the " +
					"transfer sent more than anyone realised. Neither figure blocks the transfer: it is " +
					"there to be judged, not enforced.",
			},
		],
		examples: [
			{
				type: "do",
				label: "One item drawn from three batches",
				text: "ISA100 taken from three batches appears as a single line — planned drawing weight, planned transfer weight and excess all added up, with “3 batch rows” underneath. Measure the off-cut once and it applies to the item.",
			},
			{
				type: "dont",
				label: "Don't expect it to fill itself in",
				text: "The system can calculate the excess weight, but not its shape. Leave the dimensions blank and no consolidated row is booked — only the ordinary rounding surplus is recorded, exactly as before this tab existed.",
			},
		],
		notes: [
			"<b>It updates when you open it.</b> The tab is rebuilt from the transfer tab's live figures each time you switch to it, so it always reflects the current ticks and Sec Nos. What you have typed is remembered when you switch back and forth.",
			"<b>What Transfer writes.</b> Each measured item gets one row in the <b>Excess Material</b> table on the plan, with your dimensions, the measured Kg as the quantity, and the system figure and difference recorded in its reason line — so a row that does not reconcile says so on its face rather than only in the popup that created it.",
			"<b>Transferring the same item twice accumulates</b> into that one row rather than piling up new ones. A row already returned to stock, or claimed by another plan through Excess Material Mapping, is left alone and a fresh row started instead.",
			"<b>It replaces the old per-batch excess panel.</b> That one asked for the same item's off-cut once per batch, and only ever appeared on a line already over plan — so in practice it was never seen. Where you measure here, the per-batch rounding surplus is not booked as well; the same off-cut is never recorded twice.",
			"<b>Nothing here blocks the transfer.</b> Leave the tab untouched and everything behaves exactly as it did before it existed.",
		],
	},
	{
		id: "cnc",
		title: "CNC Routing",
		kicker: "Two legs, two Stock Entries",
		purpose:
			"Material flagged <b>CNC Process</b> in Material Planning must reach the CNC " +
			"warehouse before it reaches the supplier. That is a routing instruction, not a " +
			"preference, so it is enforced rather than assumed.",
		steps: [
			"<b>Transfer → To CNC Warehouse</b> sends the flagged rows to CNC.",
			"Machining happens. Only material that has physically arrived can be forwarded.",
			"<b>Transfer → CNC to Supplier/WIP</b> appears once there is something at CNC, and moves it onward as a SEPARATE Stock Entry. Partial forwarding is supported — release it as machining finishes.",
		],
		examples: [
			{
				type: "dont",
				label: "Don't leave CNC Warehouse blank on a plan with CNC rows",
				text: "The transfer is BLOCKED outright, not warned about. With no CNC warehouse the flag would be quietly ignored and the material would go straight to the supplier, skipping the machining step — and by the time anyone noticed, the stock would have moved.",
			},
			{
				type: "do",
				label: "Two ways to clear that block",
				text: "Either set the CNC Warehouse here, or untick CNC Process on those rows back in Material Planning if the step is genuinely not required. The block message offers both.",
			},
		],
	},
	{
		id: "process-loss",
		title: "Process Loss — Not Returned",
		kicker: "Where the last few kilos went",
		purpose:
			"You send 1,836 Kg to the supplier. The job needs 116 Kg. The supplier sends " +
			"back 1,450 Kg. So where are the other 270 Kg? This is where you answer that " +
			"and close it. Until you do, the plan cannot be marked Completed.",
		fields: [
			{ name: "Used in FG (Kg)", note: "How much the job really used. Not how much you sent. You send whole pieces — a 5 metre bar to make a 340 mm part — but only the 340 mm belongs to the job. The rest is still yours." },
			{ name: "Actual Excess Returned (Kg)", note: "How much really came back. It is often not what you planned, because the off-cut gets measured again on the way back. You planned 1,500 Kg at 150×50; it came back as 1,450 Kg at 140×50." },
			{ name: "Process Loss — Not Returned (Kg)", note: "Sent, minus used, minus returned. This is real stock still sitting in the supplier's warehouse in your name. It stays there until you write it off." },
			{ name: "Process Loss Reason", note: "What the supplier told you happened to it. You must type something — a write-off with no reason is not a reason." },
			{ name: "Process Loss Warning Above (%)", note: "In Manufyxinvenza Settings, 5% to start. If the loss is bigger than this share of what you sent, the screen warns you: this is too much to be cutting loss. It only warns — you can still go ahead." },
		],
		steps: [
			"Make the Final Stock Entry first. The button does not show before that. Until the finished goods are booked, material at the supplier is still work in progress, not loss.",
			"Click <b>Process Loss</b>. It shows you the full picture: sent, used, returned, and what is left.",
			"If some excess was promised back but never came, it tells you. You choose: return it now, or tick the box to say it is not coming and write it off with the rest.",
			"If another Material Planning has already claimed that material, it stops and names the plan and the row. Free it there first — another job is counting on that steel.",
			"Type the reason and confirm. A Material Issue is created to take the weight out of the supplier's warehouse. Submit it.",
			"Now nothing of this job is left at the supplier, so the plan can move to Completed.",
		],
		calcs: [
			{
				title: "Where 1,836 Kg went",
				item: "NPB600", group: "Structurals",
				formula:
					"Transferred 1,836.934 · Used in FG 116.681 · Returned 1,450 (re-measured 140×50, " +
					"not the 1,500 planned at 150×50)",
				result: "Process Loss 270.253 Kg",
				note:
					"1,836.934 − 116.681 − 1,450 = 270.253 Kg. It is made of two things: 220 Kg that " +
					"was never going to come back, and 50 Kg that was promised but came back short. " +
					"You write off both together, with one reason.",
			},
		],
		examples: [
			{
				type: "do",
				label: "Ask the supplier before you write anything off",
				text: "That is what the reason box is for. “Cutting loss on 12 m plate, supplier confirmed” tells the next person what happened. A blank box tells them nothing, and the system will not accept one.",
			},
			{
				type: "dont",
				label: "Don't write off 1,000 Kg as process loss",
				text: "Over 5% of what you sent, the screen tells you straight: a loss that big is not cutting loss. The supplier did not use the material properly. That is a purchase return, so you get your money back — not a write-off. You can still go ahead if you really mean to, but write down why.",
			},
		],
		notes: [
			"<b>Billed to Consume has been removed.</b> It used to mean “this off-cut is never coming back” — it stayed at the supplier and the final Stock Entry swallowed it. Anything that does not come back is Process Loss now, and you say why. One change to note: with the old tick the cost went onto the job. As Process Loss it goes to the write-off account instead.",
			"Every kilo has to land somewhere: <b>Sent = Used in FG + Returned + Process Loss</b>. The plan will not close until those add up. And it checks the real stock in the warehouse, not the numbers on the screen — so it cannot be fooled by a stale figure.",
		],
	},
	{
		id: "excess-return",
		title: "Excess Material Items",
		kicker: "Getting the leftovers back",
		purpose:
			"Everything left over after the job — the surplus from rounding Sec Nos up, whatever " +
			"was measured on the transfer popup's <b>Consolidate item for excess return plan</b> " +
			"tab, and whatever the shop floor measures once the material is actually cut. Each " +
			"row is either returned to your warehouse as a real batch, or claimed directly by " +
			"another job while it is still at the supplier.",
		fields: [
			{ name: "Length / Width / Sec Nos", note: "The off-cut's real dimensions. Rows planned on the transfer popup's second tab arrive with what you measured there. Rounding-surplus rows arrive with placeholder dimensions (one standard piece) — overwrite them with what you actually measure." },
			{ name: "Return Reason", note: "Mandatory before a return entry can be created — it is what makes the returned stock explainable months later." },
			{ name: "Availability", note: "Allocated and Available, in Sec Nos and Kg — how much of this off-cut other jobs have claimed and how much is still free." },
			{ name: "Unlink Claim", note: "Releases a Material Planning's claim so the dimensions can be corrected. The off-cut then goes back into the picker for anyone to claim." },
		],
		calcs: [
			{
				title: "One off-cut, shared between jobs",
				item: "Plate 5mm", group: "Plates",
				length: 1000, sec_qty: 6, unit_weight: 7.85,
				formula:
					"A 1000 × 500 × 5 off-cut, 6 pieces at (1000÷1000) × (500÷1000) × 5 × 7.85 = 19.625 Kg each. " +
					"Job B claims 2, Job C claims 3",
				result: "5 pieces claimed (98.125 Kg) · 1 piece (19.625 Kg) still free",
				note:
					"Claiming does not create a Stock Entry — it is a promise against a specific off-cut. " +
					"The claiming rows show Batch blank with Status “Excess Mapped (Pending Return)”. When " +
					"the off-cut is physically returned, the new batch attaches itself to every row holding " +
					"a piece, and no one has to re-pick anything.",
			},
		],
		examples: [
			{
				type: "dont",
				label: "Don't change the size of an off-cut someone has claimed",
				text: "It is refused, naming the Material Planning that holds it — from this grid, from the raw-material row's Excess fields, and from the Return Excess dialog alike. Another job planned around that exact piece; shrinking it would only surface at their transfer, far too late to fix cheaply.",
			},
			{
				type: "do",
				label: "The measurement was wrong — Unlink Claim",
				text: "Release it, correct the dimensions on the raw-material row's Excess Length/Width, then let it be claimed again. Note the risk the confirmation warns about: while unlinked, another job can take it first.",
			},
			{
				type: "do",
				label: "Edit the raw-material row, not this grid",
				text: "For an off-cut created from a raw-material row, that row's Excess Length/Width/Sec Qty are the source of truth — this grid is recalculated from them on every save. The exception is a rounding-surplus row, which has no raw-material row behind it and is edited here directly.",
			},
		],
		notes: [
			"Return Excess Entry creates one Material Receipt for every unreturned row, into the Finished Goods Warehouse, and the batches it creates are traceable back to the off-cut they came from.",
		],
	},
	{
		id: "finish",
		title: "Finishing the Job",
		kicker: "Final stock entry and completion",
		purpose:
			"Once every operation on the Job work order is complete, the finished goods are " +
			"received and the plan closes itself.",
		steps: [
			"<b>Make Final Stock Entry</b> appears as soon as the <b>last operation exists</b>, and books whatever that operation has finished — you do not wait for the whole job. It first shows you what it is about to book: one line per drawing, with how many pieces are planned, how many the last operation has completed, how many are already in finished goods, and how many this entry would book. Agree with it and it creates a draft Manufacture Stock Entry to review and submit.",
			"<b>Four drawings of ten books four drawings.</b> Only the raw material belonging to those four is consumed — the rest stays at the supplier for the next entry — and only those four appear as finished goods. Finish the other six later and press it again; pieces already booked are never booked twice.",
			"The plan moves to <b>Completed</b> by itself once finished goods have been received AND every Excess Material Items row is resolved: returned, or claimed by another job — and nothing of the job is still sitting at the supplier. Anything that did not come back must have been written off as Process Loss first.",
			"Completed is one-way. The document locks; nothing later moves it back.",
		],
		notes: [
			"If the plan will not complete, it is nearly always an unresolved excess row — check that table before anything else.",
		],
	},
	{
		id: "buttons",
		title: "Every Button",
		kicker: "Quick reference",
		purpose: "What each action does, in one place.",
		fields: [
			{ name: "Refresh Raw Materials", note: "Rebuilds the list from Material Planning. Anything typed on a row is lost." },
			{ name: "Validate Stock", note: "Read-only preview of exactly what this plan will hand over: Kg and Sec Nos per item and batch, fractional totals in amber, shortfalls in red. Changes nothing — use it before transferring." },
			{ name: "Select Materials to Transfer", note: "The main transfer popup. Source → Supplier/WIP." },
			{ name: "To CNC Warehouse", note: "First leg for CNC-flagged rows. Only appears when a CNC Warehouse is set." },
			{ name: "CNC to Supplier/WIP", note: "Second leg. Only appears once material has physically arrived at CNC." },
			{ name: "Return Excess Entry", note: "Review quantities and enter a mandatory reason per row, then the return Stock Entry is created into the Finished Goods Warehouse." },
			{ name: "Make Final Stock Entry", note: "Draft Manufacture entry for the finished goods. Appears once the final operation exists, and needs at least one completed piece on it. Books only the drawings that operation has finished, and consumes only their share of the raw material." },
			{ name: "PDF", note: "A shareable batch plan — DUNO/Mark No, Customer Drawing No, planned Kg, batch details and Sec Qty — for the production or supplier team." },
		],
	},
];

const ERP_MANUAL_REPORTS_CHILDREN = [
	{
		id: "overview",
		title: "Checking Overall Stock & Reports",
		kicker: "Outside any one Material Planning",
		kind: "info",
		purpose:
			"Everything in Material Planning shows stock from the point of view of ONE document. " +
			"To see overall, warehouse-wide stock — or to check specifically what needs chasing — " +
			"use the reports below instead of piecing it together from individual plans.",
		steps: [
			"<b>Manufyxinvenza Stock Balance</b> — open from the Awesomebar. Item-and-batch-wise on-hand quantity, what's reserved against which Material Planning, and what's genuinely free — the same free-Kg figures the Exact Match and Excess Material Mapping pickers use internally, but for every item and warehouse at once.",
			"<b>Excess Material Return Report</b> — the chase-list for off-cuts. Defaults to “Pending Return” (still out there) over the last three months, and names every Material Planning holding a piece of each off-cut.",
			"<b>Cut Sheet Report</b> — which plates are cut, who is drawing from them, and what is left. “W2 Not Written” filters to sheets that have been cut but never had their balance written back to the batch — the state where the plate in the rack and the system disagree.",
		],
	},
	{
		id: "rpt-production",
		title: "Production Report",
		kicker: "One row per drawing, every operation across the columns",
		purpose:
			"The whole life of a drawing on one line. Read left to right and you walk the job " +
			"forward in the order it actually runs — what was issued, where each operation " +
			"stands, how many inspection rounds it took, how long it waited — and finish on " +
			"the weights, the costs and what has been completed.",
		fields: [
			{ name: "What appears", note: "Every <b>submitted Job Work Order</b>, one row per drawing on it — from the moment the order is submitted, before a gram of steel has been issued. A draft or cancelled order is not a job yet and does not appear." },
			{ name: "Filters", note: "Production Plan (Team), Job Type, Job Work Order, Supplier, Sales Order, Operation, Status, and a From/To date range on the Job Work Order's own date. <b>Operation</b> and <b>Status</b> are questions about operations, so they narrow the jobs as well — asking for an Open Fit-up lists the jobs that have one." },
			{ name: "Traceability columns", note: "Sales Order, Customer, Project, Production Plan (Team), Job Type, Job Work Order, Supplier, Drawing, DUNO/Mark No, Cust Drawing No, Created On — sales-order-wise, the way the report is read." },
			{ name: "Operation blocks", note: "One block per operation the job is routed through, in sequence order: <b>quantity</b>, <b>Status</b>, <b>Inspection Rounds</b>, <b>Last Inspection Status</b> and <b>Gap (Days, approx.)</b>. The first operation is measured in Kg — it is where raw material is issued — and every later one in Nos." },
			{ name: "Weight and quantity columns", note: "Customer Weight (Kg), Planned Weight (Kg), Planned Sec Nos, <b>Waste %</b>, Transferred Weight (Kg), Transferred Sec Nos — the planned-versus-actual comparison, in both weight and pieces. All the weights are for the whole drawing row." },
			{ name: "Waste %", note: "Planned Weight measured against Customer Weight — how much more steel the job buys than the finished part weighs. Cutting a member out of a length leaves an off-cut, so a few percent is normal; a line well outside its neighbours is a cutting plan worth looking at. Blank when there is no customer weight to measure against, and <b>red when negative</b>, which means the plan holds less material than the part weighs and cannot be cut." },
			{ name: "Cost columns", note: "<b>Consumed RM Cost</b> (what the material issued to this drawing was worth, from the Stock Entries that issued it — priced per Kg and spread over the Material Issue Plan's rows in proportion to what each drawing actually took, since a transfer consolidates several drawings' requirements into one line), <b>Rate Schedule</b> and <b>Rate / Kg</b> off the drawing itself, and <b>Consumables (Nos)</b> / <b>Consumable Cost</b> from the job’s Material Consumption for Manufacture entries." },
			{ name: "Excess columns", note: "<b>Excess Weight (Kg)</b> booked by the Material Issue Plan transfer popup, <b>Returned Excess Weight (Kg)</b> already brought back in, and <b>Difference (Kg)</b> — what is still out there." },
			{ name: "Completion columns", note: "<b>Completed Drawing Weight (Kg)</b> — the pieces finished, valued at the drawing’s own weight per piece — and <b>Completed Drawing (Nos)</b>." },
		],
		notes: [
			"<b>A new job is not an empty report.</b> The rows come from the Job Work Order, not from its operation entries, so a job submitted this morning already shows its drawings, its planned weights and an empty row of operations waiting to be worked. It used to be absent altogether until the first operation entry was raised.",
			"<b>It used to be one row per drawing per operation.</b> A four-operation job with six drawings filled twenty-four rows with the same six drawings repeated, and “where is 1B1 up to” meant reading four of them at once. Each drawing now has one row and the operations sit across it.",
			"<b>The operation columns are not a fixed list.</b> They are whatever the jobs in view are routed through — a job through Welding and Blasting shows those, a job through Fit-up and Painting shows those, and a view holding both shows all four.",
			"Operation Gap is still the column to sort by when looking for stalled work: a large gap on an operation that is still Open is a job nobody has picked up.",
			"<b>Created On is the Job Work Order’s own date</b>, not the date each operation entry happened to be raised — so one job reads as one date instead of four.",
			"<b>Waste % is the quickest read on the whole report.</b> Every drawing on a job is cut the same way, so the figures should sit close together. When they do not — one drawing at 104% beside another at 1.6% — it is rarely the cutting: it is two columns being compared on different bases, which is exactly the fault it was added after.",
			"<b>The consumable and excess figures are job-level</b> and repeat on every drawing row of the job. An off-cut belongs to a batch and a welding rod to a job; neither can honestly be split between drawings, so they are shown whole rather than apportioned. Read them once per job.",
			"<b>Difference</b> is the excess you declared, less what has come back. It is what is still out there — either waiting to be returned, or waiting to be written off as Process Loss.",
		],
	},
	{
		id: "rpt-inventory",
		title: "Inventory Report",
		kicker: "Ordered, received, issued and left — per item",
		purpose:
			"An order-to-issue summary per item, tied to the Sales Order or Project it belongs to. " +
			"Where the Stock Balance report answers “what is on the rack”, this one answers “how " +
			"much of what we ordered has actually turned up, and how much has gone out again”.",
		fields: [
			{ name: "Filters", note: "Sales Order, Project, Item Code, Company, and a From/To date range." },
			{ name: "Columns", note: "Item Code, Item Name, Item Group, Sales Order, Customer, Project, Ordered Qty, Received Qty, <b>Pending Receipt</b>, Issued Qty, <b>Closing Stock (Overall)</b>, UOM." },
		],
		notes: [
			"Pending Receipt is the chase-list column for purchasing — ordered but not yet delivered.",
			"Closing Stock is overall, not filtered to the Sales Order on the row, so it answers “is there any of this item anywhere” rather than “is there any reserved for this job”.",
		],
	},
	{
		id: "rpt-inspection-status",
		title: "Inspection Status Report",
		kicker: "Every inspection round, and how many retries it took",
		purpose:
			"One row per inspection round across both kinds of inspection — operations and incoming " +
			"goods. This is where rework shows up as a number rather than as an impression.",
		fields: [
			{ name: "Filters", note: "Source (which kind of document the inspection belongs to), Operation, Inspection Status, Production Plan, Sales Order." },
			{ name: "Traceability columns", note: "Production Plan, Project, Sales Order, Customer, Supplier, Reference Type, Reference, Active Doctype, Active Document, Operation." },
			{ name: "Round columns", note: "<b>Round No</b>, <b>Rework Attempts</b>, Inspection Call Date, Inspection Status, Round Status." },
			{ name: "Quantity columns", note: "Total Checked Qty, Cleared Qty, Rework Qty, Rework Remarks." },
		],
		notes: [
			"Sort by Rework Attempts to find the drawings or suppliers that keep coming back — the report exists mainly to make that pattern visible.",
		],
	},
	{
		id: "rpt-fund-usage",
		title: "Customer Fund Usage",
		kicker: "Which customer payment is paying which supplier",
		purpose:
			"Ties supplier payments back to the customer money that funded them. A customer's " +
			"Payment Entry is nominated as a <b>Source of Funds</b> on a supplier Payment Request, " +
			"and this report shows how much of each customer payment has been drawn down and what " +
			"is left.",
		fields: [
			{ name: "Filters", note: "Customer, Sales Order, Source of Funds, Status, and Group by Customer Payment." },
			{ name: "Source columns", note: "Source Reference No, Source of Funds, Reference Type, Reference Name, Source Customer, Customer Payment Date, Total Customer Payment, <b>Balance Remaining</b>." },
			{ name: "Draw columns", note: "Supplier, Payment Type, Against, Grand Total, Payment Request, Transaction Date, Outstanding, Status, PE Created." },
			{ name: "Source of Funds (on the Payment Request)", note: "Searchable by customer name, Payment Entry name or reference number, and restricted to <b>submitted customer receipts</b> — you cannot nominate a supplier payment or an unsubmitted one as a source." },
			{ name: "Total Customer Payment / Already Used Amount / Balance Amount", note: "Shown read-only on the Payment Request itself. Already Used is the sum across every other <b>Paid</b> supplier Payment Request drawing on the same source, so the balance reflects real commitments rather than drafts." },
		],
		notes: [
			"Requesting more than the remaining balance shows an orange <b>Fund Balance Exceeded</b> warning naming the amount, the balance and the source — but it does not block the save. It is there to make an overdraw a deliberate decision, not to prevent one.",
			"Only Paid requests count against a source. A draft or unpaid request does not reduce the balance.",
		],
	},
];

const ERP_MANUAL_GLOSSARY_CHILDREN = [
	{
		id: "overview",
		title: "Glossary",
		kind: "glossary",
		kicker: "Terms used across this manual",
		fields: [
			{ name: "Exact Match", note: "A batch whose own Length/Width/Thickness are EQUAL to what's required — not just “close” or “big enough.”" },
			{ name: "Reserve", note: "A soft claim on stock — marks it as spoken for so nothing else can also claim it. Always just the row's own quantity, never the whole batch. No physical movement happens yet." },
			{ name: "Sec Qty / Sec Nos", note: "The same idea under two names used interchangeably across the app — a count of physical pieces (bars, plates, cut pieces). Fractional at planning time, whole when material actually moves." },
			{ name: "Alternate Item", note: "A substitute item used in place of what was originally required." },
			{ name: "Consolidated", note: "Multiple drawings' requirements for the same item code, combined into one purchasing line." },
			{ name: "Pending Return", note: "An off-cut claimed by a job while it is still at the supplier. No batch, no stock entry — a promise, until it physically returns. If an off-cut is never coming back, its own job writes it off as Process Loss instead." },
			{ name: "CNC Process", note: "Marks that a piece needs CNC cutting at your own facility before it can go to the supplier — routes it through the Material Issue Plan's CNC Warehouse first." },
			{ name: "W1 / W2", note: "On a Cut Sheet: W1 is the piece being cut, W2 the remnant left on the plate afterwards." },
			{ name: "DUNO / Mark No", note: "The drawing-level identifier that keeps every row traceable back to exactly which piece, on which drawing, it belongs to." },
			{ name: "Job work order", note: "Display name only — the same Subcontracting Order doctype underneath, created from a Production Plan, driving every operation whether performed in-house or by a supplier." },
			{ name: "Consumption Log", note: "Where completed Nos (pieces) are logged, per drawing, on a Supplier Operation Entry — the source of truth for what's been done at that operation." },
			{ name: "Inspection Mandatory", note: "A per-operation flag (set on Production Plan's Operation table) that requires an Inspection Entry to accept quantity before it counts as Completed." },
			{ name: "Reqd Qty vs Issued Qty", note: "On a Material Issue Plan row: what must be transferred, versus what has gone so far. Equal when the row is fully issued." },
			{ name: "Excess Qty vs Transfer Excess Kg", note: "The first is the mapped batch measured against the drawing's planned weight, set when the row is fetched. The second is surplus created by rounding Sec Nos up at transfer time." },
			{ name: "Finished Goods Warehouse", note: "The Material Issue Plan field that receives both the finished good (Make Final Stock Entry) and any off-cut/unconsumed material (Return Excess Entry)." },
		],
	},
];

// ─── Purchase & Procurement — what happens between Material Planning saying
// "this isn't in stock" and the batch arriving that satisfies it. The same
// custom dimension fields (Parent Item Group, Length/Width/Thickness, Unit
// Weight, Sec Qty) ride the entire chain, copied forward at each hop, which is
// why the qty formula and its missing-field check are identical on all four
// documents (utils/dimension_formula.py). ──────────────────────────────────────
const ERP_MANUAL_PROCUREMENT_CHILDREN = [
	{
		id: "proc-overview",
		title: "From Shortfall to Stock",
		kicker: "Where Material Planning hands over",
		purpose:
			"Material Planning decides <i>what is missing</i>; this chain is how it gets bought. " +
			"Unavailable Items and Consolidate Item both end in a Material Request, and from there " +
			"the material travels through the normal purchasing documents until a Purchase Receipt " +
			"creates the batch that Material Planning was waiting for.",
		steps: [
			"<b>Material Planning</b> → <b>Create Material Request</b>, from either the Unavailable Items table (one row per shortfall) or the Consolidate Item table (several drawings' needs for the same item combined into one buying line).",
			"<b>Material Request</b> → optionally <b>Request for Quotation</b> to several suppliers, and their replies come back as <b>Supplier Quotations</b>.",
			"<b>Purchase Order</b> against the chosen supplier — created from the Material Request, or from the winning Supplier Quotation.",
			"<b>Purchase Receipt</b> when the material physically arrives. Submitting it creates the batch, carrying the dimensions and piece count down from the receipt line.",
			"Back on <b>Material Planning</b>, the new batch is offered against the rows that were waiting for it — covered in <b>After Purchase: Automatic Allocation</b> under Material Planning.",
		],
		fields: [
			{ name: "The fields that travel the whole way", note: "<b>Parent Item Group</b> and <b>Item Calculation Type</b> (both read-only, pulled from the Item), <b>Length</b>, <b>Width</b>, <b>Thickness</b>, <b>Unit Weight</b> (read-only), <b>Sec Qty</b> and <b>Sec UOM</b>. Every document in the chain carries the same set, so the piece being bought stays described the same way from request to receipt." },
			{ name: "The traceability fields", note: "<b>Drawing</b>, <b>DUNO/Mark No</b>, <b>Customer Drawing Number</b> and <b>Sales Order</b> ride along on Material Request, Purchase Order and Purchase Receipt rows, so a delivered bar can always be traced back to the drawing that asked for it." },
			{ name: "Material Planning (on the Material Request)", note: "Set automatically when the request was raised from a Material Planning's own Create Material Request button. This link is what lets the plan find its own purchases later." },
		],
		notes: [
			"Qty on Structurals and Plates rows is never typed in directly — it is recalculated from the dimensions on every save, on all four documents. Type the dimensions and the piece count; the Kg follows.",
			"With <b>Auto Purchase from Material Planning</b> ticked in Manufyxinvenza Settings, an Auto Purchase button on Material Planning runs Material Request → Purchase Order → Purchase Receipt in one click for every unavailable item. That is a testing and data-entry shortcut, not a live purchasing process — see <b>Settings</b> under Reference.",
		],
	},
	{
		id: "proc-mr",
		title: "Material Request",
		kicker: "The shortfall, written down",
		purpose:
			"The first document in the chain, and normally created for you by Material Planning " +
			"rather than by hand. Each row describes one piece to buy, in the same dimension " +
			"language the rest of the app uses.",
		fields: [
			{ name: "Material Planning", note: "Header link back to the plan that raised this request. Left blank on a manually-created request." },
			{ name: "Parent Item Group / Item Calculation Type", note: "Read-only, copied from the Item. Parent Item Group is what decides which formula applies to this row — Structurals, Plates and Nuts and Bolts each behave differently." },
			{ name: "Length / Width / Thickness", note: "In millimetres. Structurals need Length only; Plates need all three." },
			{ name: "Unit Weight", note: "Read-only, from the Item. Kg per metre for a Structural, Kg per mm per square metre for a Plate." },
			{ name: "Sec Qty / Sec UOM", note: "How many pieces are being requested, and in what unit. Sec UOM is read-only." },
			{ name: "Drawing / DUNO Mark No / Customer Drawing Number / Sales Order", note: "Traceability back to what needs the material." },
		],
		calcs: [
			{
				title: "Qty for a Structural row",
				item: "ISMB400", group: "Structurals",
				length: 6000,
				sec_qty: "3 Nos", unit_weight: "61.6 kg/m",
				formula: "(Length ÷ 1000) × Unit Weight × Sec Qty = (6000 ÷ 1000) × 61.6 × 3",
				result: "1108.80",
				note: "Length is converted from mm to metres first, which is what the ÷ 1000 is doing.",
			},
			{
				title: "Qty for a Plate row",
				item: "PLATE10", group: "Plates",
				length: 6000, width: 1500, thickness: 10,
				sec_qty: "2 Nos", unit_weight: "7.85",
				formula: "(Length ÷ 1000) × (Width ÷ 1000) × Thickness × Unit Weight × Sec Qty = (6000 ÷ 1000) × (1500 ÷ 1000) × 10 × 7.85 × 2",
				result: "1413.00",
				note: "Both Length and Width convert to metres; Thickness stays in mm, because Unit Weight for a plate is already expressed per mm of thickness.",
			},
		],
		steps: [
			"Enter the dimensions and Sec Qty on each row. Qty (Kg) recalculates itself on every save — there is no need to work it out.",
			"<b>Nuts and Bolts run the other way round.</b> Enter Qty in Nos and Sec Qty is calculated as Unit Weight × Qty, because for fasteners the piece count is the real number and the weight is derived.",
			"Saving with a required dimension missing shows an orange warning naming the row and the missing fields, but still saves — so a part-finished request can be parked.",
			"Submitting with anything still missing is refused outright with the same message. The warning on save is the reminder; the block on submit is the gate.",
		],
		notes: [
			"The UOM field on a row only offers that item's own UOM conversions plus its stock UOM, rather than every UOM on the system.",
			"Required for a <b>Structural</b>: Length, Unit Weight, Sec Qty. Required for a <b>Plate</b>: Length, Width, Thickness, Unit Weight, Sec Qty. Any other item group is left alone entirely.",
		],
	},
	{
		id: "proc-rfq-sq",
		title: "RFQ and Supplier Quotation",
		kicker: "Asking several suppliers, and reading their answers",
		purpose:
			"Optional middle step. A Request for Quotation takes the Material Request's rows out to " +
			"several suppliers; each reply comes back as a Supplier Quotation, and the winning one " +
			"can be turned straight into a Purchase Order.",
		fields: [
			{ name: "On RFQ rows", note: "Parent Item Group, Item Calculation Type, Sec Qty, Sec UOM, Unit Weight, Length, Width, Thickness — all copied from the linked Material Request Item, and all read-only here." },
			{ name: "On Supplier Quotation rows", note: "The same set, but Length, Width, Thickness and Sec Qty are editable — a supplier may quote a slightly different size to what was asked for, and that has to be recordable." },
		],
		steps: [
			"Create the RFQ from the Material Request and add the suppliers to invite.",
			"Each row's dimensions are copied down from the Material Request Item automatically.",
			"Supplier replies arrive as Supplier Quotations, which copy the same fields across — but only into fields that are still blank, so anything the supplier actually quoted differently is left as they quoted it.",
			"Qty on a Supplier Quotation recalculates from its dimensions on save, exactly as on the Material Request, and the same missing-field check runs on submit.",
		],
		examples: [
			{
				type: "dont",
				label: "Don't edit dimensions on the RFQ row",
				text: "RFQ rows re-copy from the Material Request Item on <b>every</b> save, overwriting whatever is there. An edit made on the RFQ will not survive the next save. Change it on the Material Request instead, and let it flow down.",
			},
			{
				type: "do",
				label: "Do edit them on the Supplier Quotation",
				text: "Supplier Quotation, Purchase Order and Purchase Receipt only fill fields that are <b>blank</b>. Once a value is there, later saves leave it alone — so a supplier's own quoted size stays put.",
			},
		],
	},
	{
		id: "proc-po",
		title: "Purchase Order",
		kicker: "Committing to the supplier",
		purpose:
			"The order itself. Created from the Material Request or from the winning Supplier " +
			"Quotation, and carrying the drawing references forward so the delivered material can " +
			"still be tied back to the job that needs it.",
		fields: [
			{ name: "Total Weight (Kg)", note: "Read-only header total, recalculated on every save. It sums the Qty of <b>Structurals and Plates rows only</b> — Nuts and Bolts are counted in pieces, so adding their Qty into a Kg total would be meaningless." },
			{ name: "Drawing / DUNO Mark No / Customer Drawing Number / Sales Order", note: "Copied from the linked Material Request Item when the order is raised from a request, and only into fields still blank." },
			{ name: "Length / Width / Thickness / Sec Qty", note: "Editable. Qty recalculates from them on save, the same way as everywhere else in the chain." },
		],
		steps: [
			"Create the order from the Material Request (or the Supplier Quotation) rather than from scratch, so the references come with it.",
			"Qty recalculates on save; a row missing a required dimension warns in orange but still saves.",
			"On submit, any row still missing a required dimension blocks the submission.",
		],
		notes: [
			"A Purchase Order raised outside this chain — straight from the supplier, with no Material Request behind it — still works. It just has nothing to copy references from, so Drawing and Sales Order stay blank unless filled in by hand.",
		],
	},
	{
		id: "proc-pr",
		title: "Purchase Receipt",
		kicker: "Material arrives, batches are born",
		purpose:
			"The point where a purchase becomes stock. Submitting a Purchase Receipt creates one " +
			"batch per line, carrying that line's dimensions and piece count onto the batch, which " +
			"is what makes the material findable by Material Planning's Exact Match.",
		fields: [
			{ name: "Supplier Invoice Weight / Weighment Weight", note: "What the supplier's paperwork claims, and what the weighbridge actually read. Recorded side by side so a discrepancy is visible at receipt rather than discovered later." },
			{ name: "Total Weight (Kg)", note: "Read-only, the received total." },
			{ name: "Target / Source / Rejected Storage Location", note: "Per-row physical location within the warehouse. Rejected Storage Location is where QC-failed material is put aside." },
			{ name: "Inspection Status / Inspection Call Log", note: "Present when any item on the receipt has <b>Inspection Required</b> ticked on its Item master. Covered in full under Inspection." },
			{ name: "Inspection Accepted Qty / Rejected Qty / Remarks", note: "Read-only per row, written back when the Inspection Entry for this receipt is submitted." },
			{ name: "Length / Width / Thickness / Sec Qty / Sec UOM", note: "Same as everywhere else in the chain — and these are the values that land on the batch, so they need to describe what actually turned up, not what was ordered." },
		],
		steps: [
			"Create the receipt from the Purchase Order so the dimensions and references come with it. Correct anything that arrived different to what was ordered <b>before</b> submitting.",
			"If any item on the receipt requires inspection, run that first — the receipt will not submit until its Inspection Status is Completed.",
			"On submit, one batch is created per line, named and dimensioned from that line. See <b>The Batch Record</b> under Item for how the name is built.",
			"<b>A receipt can also fill rows already sitting in Material Mapping</b> — the state a plan is left in when Check Stock Availability has moved its requirements out of Unavailable Items. Those rows are filled in place rather than added again, so the requirement is never duplicated, and a row the receipt can only cover in part keeps its remainder as a separate blank-batch row to assign by hand.",
			"On submit, <b>Batches Allocated — Reserve Them</b> names the Material Planning the new batches went to and opens it from the dialog. <b>Allocated is not reserved</b>: only reserved rows are offered for transfer on a Material Issue Plan, so go and reserve them. Reserve the last one and the plan's status moves to Batch Mapping Completed by itself.",
			"<b>If nothing was allocated, the receipt now says why.</b> Allocation follows the chain <b>Receipt line → Purchase Order line → Material Request line → that request's Material Planning</b>, and it only takes one missing link — a Purchase Order raised by hand instead of from the request, say — for the batches never to reach the plan. The receipt names the first broken link per item instead of submitting in silence. An ordinary purchase with no plan behind it stays quiet, as it should.",
			"<b>Material Planning → Allocate to Material Planning</b> runs the allocation again on a submitted receipt, once the chain is repaired — so a receipt that missed its plan does not have to be cancelled and re-entered for stock that has already arrived. Safe to press twice: a requirement already covered has nothing left to match.",
		],
		buttons: [
			{ name: "Create Inspection", note: "Logs an inspection call round against this receipt, then offers to create the Inspection Entry that records the result." },
			{ name: "Update Inspection Call Date", note: "Changes the call date on the round already logged, for when QC's visit is rescheduled rather than newly arranged." },
			{ name: "View Inspection Entry", note: "Jumps to the Inspection Entry already created for the current round." },
		],
		notes: [
			"Material received against a Material Planning does not reserve itself. It becomes available stock, and the plan then offers it against the rows that were waiting — see <b>After Purchase: Automatic Allocation</b> under Material Planning.",
			"Two rows for the same item with identical Length, Width and Thickness cannot be matched to their batches reliably, and the receipt is refused with a message saying so. Give them distinct dimensions, or split them across two receipts.",
		],
	},
];

// ─── Reference — the lookup material that doesn't belong to any one screen:
// every document's status flow in one place, and the settings that change what
// the rest of the app shows. Status values here are the actual Select options on
// each doctype, not a description of them. ─────────────────────────────────────
const ERP_MANUAL_REFERENCE_CHILDREN = [
	{
		id: "ref-statuses",
		title: "Document Status Reference",
		kicker: "Every status flow, in one place",
		purpose:
			"What each document's status can be, and what moves it along. Useful when a document " +
			"is sitting in a state you did not expect and the question is simply what is supposed " +
			"to happen next.",
		fields: [
			{ name: "Drawing", note: "<b>Working → Old Revision / Final Revision</b>. A drawing stays Working while it is being edited. Marking it Final Revision is what allows a BOM to be created from it; superseded revisions become Old Revision." },
			{ name: "Material Planning (Planning Status)", note: "<b>Open → Working → Batch Mapping Completed</b>. Moves to Working as soon as raw materials are fetched and mapping starts, and reaches Batch Mapping Completed only when every row has stock behind it — which is what lets a Production Plan be created." },
			{ name: "Production Plan", note: "Standard ERPNext plan statuses. What matters here is submission: <b>Job work order &amp; MIP</b> only appears once the plan is submitted." },
			{ name: "Job work order", note: "<b>Open → Working → Completed</b>. Open on submit; Working once any operation has quantity logged; Completed when every operation is submitted <i>and</i> the Material Issue Plan's Final Stock Entry is submitted. Re-derived on each of those events rather than latched, so cancelling the Final Stock Entry returns it to Working. (ERPNext's own receipt-driven statuses — Partially Received, Material Transferred — are unreachable here: a plan-driven job work order has no Subcontracting Receipt and no Raw Materials Supplied table, which is why every order used to sit on Open for its whole life.)" },
			{ name: "Material Issue Plan", note: "<b>Open → In Progress → Completed</b>. In Progress from the first partial transfer; Completed when every row has been fully issued." },
			{ name: "Supplier Operation Entry", note: "<b>Open → In Progress → Completed</b>. Logging any quantity in the Consumption Log moves it to In Progress. Completed is only accepted when every drawing has reached the quantity this operation was given and no inspection round is still Pending; setting it asks for confirmation and then submits. Every earlier operation in the sequence must already be submitted." },
			{ name: "Inspection Entry", note: "<b>Open → Working → Completed</b>, plus <b>Feedback: Ok / Not Ok</b>. Feedback must be set before Status can be set to Completed. Saving as Completed also submits, after a confirmation prompt." },
			{ name: "Inspection Status (on Supplier Operation Entry and Purchase Receipt)", note: "<b>Open → Working → Completed</b>. Not set by hand — it mirrors the status of the Inspection Entry that answered the latest round when that entry is submitted." },
			{ name: "Inspection Call Log — Round Status", note: "<b>Pending → Completed</b>, per round. Pending until that round's Inspection Entry is submitted." },
			{ name: "Cut Sheet", note: "<b>Draft → Active → Fully Allocated → Consumed</b>. Active once the cutting plan is set, Fully Allocated when every piece on the sheet has been claimed by a job, Consumed once the material has actually moved." },
			{ name: "Delivery Challan (Gate Pass)", note: "<b>Draft → Material Out → Partially Returned / Overdue → Returned</b>, with <b>Material In</b> for a Return Entry. Derived, never chosen. Overdue outranks Partially Returned so anything past its return date still reads Overdue; Returned outranks Overdue, so a late but complete return clears the flag. Cancelling a Return Entry reopens its source." },
		],
		notes: [
			"Statuses on this app's own documents are driven by what has happened to them, not chosen from a dropdown — the two exceptions are Supplier Operation Entry, where the operator marks Completed before submitting, and Inspection Entry, where the inspector sets the status and the Feedback.",
		],
	},
	{
		id: "ref-consumable-entry",
		title: "Consumable Entry",
		kicker: "Issuing consumables against a job",
		purpose:
			"Welding rods, paint and gas are consumed by a job but are not the job's own " +
			"material. Ticking <b>Consumable Entry</b> on a Stock Entry says so, and asks the " +
			"one question that decides whose cost they land on: which job.",
		fields: [
			{ name: "Consumable Entry", note: "Sits next to Inspection Required. Ticking it marks every item row as a consumable and reveals the two questions below." },
			{ name: "Sales Order", note: "Which order the consumables are being issued against. The only one of the three chosen freely. Required once the box is ticked." },
			{ name: "Production Plan", note: "Only the plans raised against that order are offered. Choosing one fills in its Job Work Order. Required once the order is chosen." },
			{ name: "Job work order", note: "Filled in for you from the plan. Where a plan has more than one, the earliest is used and you are told, so you can change it." },
		],
		steps: [
			"Tick <b>Consumable Entry</b>. Every row already on the entry is marked as a consumable, and you are told how many.",
			"Pick the <b>Sales Order</b>.",
			"Pick the <b>Production Plan</b> — the list is already narrowed to that order.",
			"The <b>Job work order</b> fills itself in. Add the consumable items and submit as normal.",
		],
		notes: [
			"<b>Both questions must be answered.</b> Sales Order and Production Plan are mandatory while Consumable Entry is ticked — the two of them are what the Job Work Order is looked up from, and the Job Work Order is what every weight rollup downstream keys on. A ticked entry with neither filled in issues stock against nothing, so it is refused on save, naming what is missing.",
			"<b>Each step clears what is below it.</b> Change the Sales Order after picking a plan and the plan and Job Work Order are cleared, because a plan belonging to a different order is a mismatch nobody would see — and this document decides whose cost the consumables land on. Saving one anyway is refused, naming both.",
			"<b>Material Consumption for Manufacture ticks it for you.</b> That type <i>is</i> a consumable entry, so the box is set and locked rather than left as a question with one right answer — and Work Order is hidden, because this flow reaches its job through Sales Order and Production Plan instead.",
			"<b>Rows added afterwards arrive ticked</b>, while Consumable Entry is on.",
			"<b>Unticking does not clear the rows.</b> A row may have been marked a consumable deliberately, and clearing somebody's rows because a header field changed is not a decision this makes for you. Untick the rows yourself if that is what you want.",
			"There used to be two Job Work Order fields on this form holding the same value — <i>Job work order</i> and <i>Subcontracting Order (PP Flow)</i>. The second is now hidden; it is still filled in behind the scenes, because a good deal of the app reads it.",
		],
	},
	{
		id: "ref-decision-log",
		title: "Decision Log",
		kicker: "Who decided what, and why",
		purpose:
			"<b>Manufyx Decision Log</b> records the handful of decisions people argue about " +
			"weeks later: who reserved a batch, who released it, who moved one job's material to " +
			"another batch, who rounded a quantity up, and what they said at the time. Open it " +
			"from the awesome bar; it is a list, not a screen anybody has to fill in.",
		fields: [
			{ name: "Decision", note: "Reserve, Unreserve, Reassign Batch, Round Up at Transfer, or Cut Sheet Balance." },
			{ name: "Reference / Row", note: "The document it was made on, and the specific row where the decision was about one row rather than a whole document." },
			{ name: "Item / Batch / New Batch", note: "What was affected. New Batch is filled in on a reassignment and on a cut sheet balance that became its own batch." },
			{ name: "Rows Affected", note: "How many rows one decision covered. Reserving a plan is one decision, not one per row." },
			{ name: "Previous Sec Qty / Sec Qty / Previous Qty / Qty", note: "The figures before and after, where the decision changed a number." },
			{ name: "Reason / Details", note: "The reason given at the time, where the screen asked for one, and a one-line account of what happened so the entry reads on its own." },
			{ name: "Created By / Created On", note: "Standard Frappe fields, and the answer to “who” and “when”. Nothing else has to record them." },
		],
		notes: [
			"<b>One entry per decision, not per field.</b> Logging every field change on every document was considered and rejected: on a 500-drawing order it would be large, slow to write and unreadable. What is here is the short list of things people actually ask about.",
			"<b>Nothing writes to it from a screen, and nothing can remove an entry.</b> No role has create, write or delete on it — the entries are made by the app at the moment the decision is taken, and that is the whole point of them.",
			"<b>It never blocks anything.</b> If an entry cannot be written, the reservation or transfer still goes through and the failure goes to the error log. A reservation that succeeded and then failed because its log entry could not be saved would be worse than having no log.",
			"Deleting the document an entry describes is still allowed — the log holds the name of what was deleted, which is often the useful part.",
		],
	},
	{
		id: "ref-settings",
		title: "Settings",
		kicker: "Three switches that change what you see",
		purpose:
			"<b>Manufyxinvenza Settings</b> is a single settings document holding the handful of " +
			"options that change how the app behaves site-wide. Two of them change which buttons " +
			"appear, so a button described in this manual but missing on your screen is usually " +
			"explained here.",
		fields: [
			{ name: "Auto Purchase from Material Planning", note: "Off by default. When ticked, an <b>Auto Purchase</b> button appears on Material Planning that creates Material Request → Purchase Order → Purchase Receipt in one click for every unavailable item — and the same switch reveals the <b>Add All Drawing</b> testing button on Supplier Operation Entry. Both are data-entry shortcuts for setting up test data. On a live site this stays off, and neither button exists." },
			{ name: "Cut Sheet Tolerance (%)", note: "Default <b>2</b>. How far To Use (W1) plus Balance (W2) may differ from the sheet actually being cut before a warning appears. Cutting always loses a little to the saw, so a small gap is normal — the warning exists to catch a mis-typed dimension, not to police the kerf. Set 0 to warn on any difference at all. It never blocks a save." },
			{ name: "Create New Batch for Cut Sheet Stock Entry", note: "Default <b>off</b>. Off: once the cut has been transferred, the sheet's own batch is rewritten to the Balance (W2) dimensions — same batch, same name, new size. On: the batch is never rewritten; a Repack Stock Entry empties it and creates a <b>new</b> batch carrying the W2 dimensions, Sec Qty and Kg, so documents already issued against the original still read true." },
		],
		notes: [
			"Turn <b>Create New Batch for Cut Sheet Stock Entry</b> on where paperwork already issued against a batch must stay accurate after the plate is cut. Leave it off where fewer batch records is worth more than that.",
			"These are site-wide settings, not per-user. Changing one changes the app for everybody.",
		],
	},
];

// ─── Delivery Challan — the pre-printed gate pass pad, in the system. Separate
// from the Material Issue Plan on purpose: this records what physically left the
// gate and whether it came back, and moves no stock at all. ─────────────────────
const ERP_MANUAL_DELIVERY_CHALLAN_CHILDREN = [
	{
		id: "overview",
		title: "Delivery Challan (Gate Pass)",
		kicker: "The paper pad, in the system",
		purpose:
			"A digital copy of the printed DELIVERY CHALLAN pad. It records what left the gate, " +
			"for whom, on whose vehicle, when it is due back, and whether it ever returned. It is " +
			"used for plain delivery-note movements and for subcontracting alike.",
		fields: [
			{ name: "Challan Type", note: "<b>Returnable</b> — material you expect back, so it needs a return date and gets chased. <b>Non Returnable</b> — it is gone for good. <b>Return Entry</b> — the inbound counterpart, raised against a Returnable pass to bring material back. Set once, when the document is created." },
			{ name: "GP No.", note: "The document name, on the <b>GP-00001</b> series. It is the gate pass number quoted on the supplier's paperwork, so it is never reused or renumbered." },
			{ name: "Status", note: "Worked out from what has happened to the document — never picked from a list. See <b>Status flow</b> below." },
			{ name: "Company", note: "Drives the printed letterhead: name, address and GST number come from this company's address record." },
		],
		notes: [
			"<b>A gate pass moves no stock.</b> Submitting one creates no Stock Entry, no Stock Ledger Entry and no reservation — it is a paper document held in the database, for gate reference and return chasing. This is deliberate and is covered by a test.",
			"It does <i>not</i> replace the Material Issue Plan. Material issued to a supplier for a job still moves through the MIP transfer; the gate pass is the slip that travels with the lorry alongside it.",
		],
	},
	{
		id: "filling",
		title: "Filling one in",
		kicker: "The form reads in the pad's own order",
		purpose:
			"The form is laid out to match the printed pad, so it can be filled straight from a " +
			"written slip without hunting for fields.",
		fields: [
			{ name: "To (Party Type / Party)", note: "Supplier, Customer, or Other for anyone not on file. <b>Name</b> fills itself the moment a party is chosen and is what prints in the To box — edit it freely if the printed name should read differently." },
			{ name: "Address", note: "Pulled from the party's own Address record. A party with no Address record leaves it blank — type it in by hand." },
			{ name: "Reference and Vehicle", note: "Read this section <i>across</i> and it is the pad's own grid: Job No. / Production Plan No / Vehicle No, then Ref. DC. No. / WO Date / Driver Name, then Expected Date of Return / Total Value of Goods / Mobile No. <b>Job No.</b> is free text; <b>Production Plan No</b> links to a real plan." },
			{ name: "Total Value of Goods", note: "Typed by hand. It is deliberately never computed from the item rows — the declared value on a gate pass is not always the stock value." },
			{ name: "Items", note: "Sl No, Material Description, UOM, Qty, Weight in Kgs, Purpose and Remarks — the pad's columns exactly. <b>Item</b> and <b>Batch</b> are extra, are not printed, and are optional: pick an Item and the description and UOM fill themselves." },
			{ name: "Terms and Conditions", note: "The pad's four clauses, filled in on save. Editable per challan if a particular consignment needs different wording." },
			{ name: "Sign-off", note: "Material Received By is free text; Production / Planning, Stores Incharge and Factory Head link to users. All four print as the four signature boxes along the bottom." },
		],
		steps: [
			"Pick the Challan Type first — it decides whether a return date is required and whether the Against Gate Pass field appears.",
			"Choose the party, then fill the reference and vehicle details from the slip.",
			"Add the material rows. Total Qty and Total Weight add themselves up as you type.",
			"Save, then Submit. Submitting is what puts the challan on the gate record — a draft is not yet a gate pass.",
		],
		notes: [
			"The Items table opens with one <b>blank row already in it</b>. Fill it or delete it — saving with an empty row is refused, because Material Description is required on every line.",
			"<b>Expected Date of Return</b> is required on a Returnable pass and cannot be earlier than the GP Date. It is cleared automatically on the other two types.",
		],
	},
	{
		id: "returns",
		title: "Returnable and Return Entry",
		kicker: "Bringing material back, in part or in full",
		purpose:
			"Material that goes out Returnable is chased until it comes back. The return is its own " +
			"gate pass — a Return Entry — pointing at the original, and it can be raised as many " +
			"times as it takes.",
		steps: [
			"Open the submitted Returnable gate pass and use <b>Create → Return Entry</b>. The new document opens pre-filled with everything still outstanding, row by row.",
			"If only part came back, reduce the quantities — or zero a row entirely — before saving.",
			"Submit it. The original updates itself immediately: Returned Qty, Pending Qty and Status all move.",
			"Repeat for each later delivery until nothing is pending, at which point the original reads Returned.",
		],
		buttons: [
			{ name: "Return Entry (under Create)", note: "Only on a submitted <b>Returnable</b> gate pass that is not yet fully Returned. Pre-fills the pending quantity per row." },
			{ name: "Original Gate Pass", note: "On a Return Entry — jumps straight back to the pass it is returning against." },
		],
		notes: [
			"Each return row is tied to <b>the row it came from</b>, not just to the item code. Two lines carrying the same item on one challan are therefore netted apart correctly — which is why returns should be raised with the button rather than built by hand.",
			"Returning more than is still out is refused, and the message names the row and the quantity actually outstanding.",
			"<b>Cancelling a Return Entry puts the material back on the original's books</b> — the source returns to Material Out or Overdue and the quantity is pending again.",
			"A Return Entry can only be raised against a <b>submitted Returnable</b> pass. Non Returnable material is gone for good, so the button refuses it.",
		],
	},
	{
		id: "status",
		title: "Status flow",
		kicker: "Draft → Material Out → Returned",
		purpose:
			"The status is derived from the document, never chosen. It answers one question: is " +
			"anything still sitting outside that should not be?",
		fields: [
			{ name: "Draft", note: "Saved but not submitted. Nothing has left the gate yet." },
			{ name: "Material Out", note: "A submitted Returnable or Non Returnable pass. For Non Returnable this is where it stays — nothing is expected back." },
			{ name: "Material In", note: "A submitted Return Entry. The inbound counterpart of Material Out." },
			{ name: "Partially Returned", note: "Some but not all of a Returnable pass has come back. Returned Qty and Pending Qty show the split." },
			{ name: "Overdue", note: "A Returnable pass past its Expected Date of Return with something still outstanding. Shown in red in the list and with a banner on the form." },
			{ name: "Returned", note: "Everything is back. This wins over Overdue — a late but complete return clears the red flag." },
			{ name: "Cancelled", note: "The document was cancelled. Cancelling a Return Entry also reopens its source." },
		],
		notes: [
			"<b>Overdue outranks Partially Returned.</b> A part-return that is past its date still reads Overdue, because the point of the status is to flag what is outside — the exact split stays readable in Returned Qty and Pending Qty.",
			"Overdue is refreshed by a daily background job <i>and</i> every time the Delivery Challan list is opened. That belt-and-braces is deliberate: on a bench whose scheduler is paused, a job-only implementation would look correct and silently never run.",
		],
	},
	{
		id: "printing",
		title: "Printing the challan",
		kicker: "A copy that matches the pad",
		purpose:
			"Both buttons render from the same layout, so what is previewed on screen and what " +
			"downloads as a PDF can never differ.",
		buttons: [
			{ name: "Print Preview", note: "Opens the challan on screen exactly as it will print — letterhead, To box, reference grid, item table with the Total row, the four terms and the four signature boxes." },
			{ name: "PDF", note: "Downloads the same thing as a single-page A4 PDF, named after the gate pass." },
		],
		notes: [
			"The letterhead — company name, address and GST number — comes from the <b>Company's own Address record</b>. If a company has several addresses and none is ticked <b>Is Primary Address</b>, one is chosen for you; tick the right one so the printed address is the one you intend.",
			"On a submitted Returnable pass the printout carries a status line underneath — Status, Returned and Pending — so a printed copy still says how much is outstanding.",
			"Purpose prints only if Gate Pass Purpose records exist to choose from — see the next page.",
		],
	},
	{
		id: "purpose-master",
		title: "Gate Pass Purpose",
		kicker: "The Purpose list on the item rows",
		purpose:
			"A small master holding the reasons material leaves — the values offered in the " +
			"Purpose column on every gate pass line.",
		fields: [
			{ name: "Purpose", note: "The name, and what prints in the Purpose column. Must be unique." },
			{ name: "Description", note: "Optional note for whoever is picking from the list." },
			{ name: "Disabled", note: "Retires a purpose. Old challans keep it; new ones are no longer offered it." },
		],
		notes: [
			"The list starts empty on purpose — these are your own words for why material goes out, not a guessed set. Add them once and they are available on every challan.",
		],
	},
];

const ERP_MANUAL_CATEGORIES = [
	...ERP_MANUAL_STUB_CATEGORIES,
	{ id: "bom", label: "BOM", children: ERP_MANUAL_BOM_CHILDREN },
	{ id: "material-planning", label: "Material Planning", children: ERP_MANUAL_MATERIAL_PLANNING_CHILDREN },
	{ id: "procurement", label: "Purchase & Procurement", children: ERP_MANUAL_PROCUREMENT_CHILDREN },
	{ id: "production-plan", label: "Production Plan", children: ERP_MANUAL_PRODUCTION_PLAN_CHILDREN },
	{ id: "job-work-order", label: "Job Work Order", children: ERP_MANUAL_JOB_WORK_ORDER_CHILDREN },
	{ id: "material-issue-plan", label: "Material Issue Plan", children: ERP_MANUAL_MATERIAL_ISSUE_PLAN_CHILDREN },
	{ id: "delivery-challan", label: "Delivery Challan (Gate Pass)", children: ERP_MANUAL_DELIVERY_CHALLAN_CHILDREN },
	{ id: "supplier-operation-entry", label: "Supplier Operation Entry", children: ERP_MANUAL_SOE_CHILDREN },
	{ id: "inspection", label: "Inspection", children: ERP_MANUAL_INSPECTION_CHILDREN },
	{ id: "reports", label: "Reports & Stock Checking", children: ERP_MANUAL_REPORTS_CHILDREN },
	{ id: "reference", label: "Reference", children: ERP_MANUAL_REFERENCE_CHILDREN },
	{ id: "glossary", label: "Glossary", children: ERP_MANUAL_GLOSSARY_CHILDREN },
];
