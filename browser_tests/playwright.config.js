// Playwright config for manufyxinvenzaerp browser tests.
//
// Uses the Google Chrome already installed on the machine (channel "chrome"), so no
// Playwright browser download is needed. Run headed with HEADED=1 to watch it work.
const { defineConfig } = require("@playwright/test");

module.exports = defineConfig({
	testDir: ".",
	testMatch: /.*\.spec\.js$/,
	// One long, ordered flow: every step depends on the one before it.
	fullyParallel: false,
	workers: 1,
	retries: 0,
	timeout: 60 * 60 * 1000,
	expect: { timeout: 20000 },
	reporter: [["list"], ["html", { open: "never", outputFolder: "playwright-report" }]],
	use: {
		baseURL: process.env.FRAPPE_URL || "http://127.0.0.1:8000",
		channel: "chrome",
		headless: !process.env.HEADED,
		viewport: { width: 1440, height: 900 },
		actionTimeout: 20000,
		navigationTimeout: 60000,
		screenshot: "only-on-failure",
		trace: "retain-on-failure",
		video: "retain-on-failure",
	},
	outputDir: "test-results",
});
