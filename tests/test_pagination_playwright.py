from pathlib import Path
import unittest

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]


class PaginationBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def setUp(self):
        self.page = self.browser.new_page()
        self.page.add_script_tag(path=str(ROOT / "web" / "features" / "pagination.js"))
        self.page.evaluate(
            """
            () => {
              document.body.innerHTML = paginationTools.paginationFooter(
                95,
                {page: 4, pages: 10, pageSize: 10},
              );
              window.requestedPages = [];
              window.requestedPageSizes = [];
              if (typeof paginationTools.bindPaginationControls === 'function') {
                paginationTools.bindPaginationControls(document, {page: 4, pages: 10}, {
                  onPageChange: value => window.requestedPages.push(value),
                  onPageSizeChange: value => window.requestedPageSizes.push(value),
                });
              }
            }
            """
        )

    def tearDown(self):
        self.page.close()

    def test_first_and_last_buttons_request_boundary_pages(self):
        if self.page.locator("#first-page").count() == 0:
            self.fail("pagination is missing the first-page button")
        if self.page.locator("#last-page").count() == 0:
            self.fail("pagination is missing the last-page button")

        self.page.locator("#first-page").click()
        self.page.locator("#last-page").click()

        self.assertEqual(self.page.evaluate("window.requestedPages"), [1, 10])

    def test_page_number_can_jump_by_button_or_enter_key(self):
        if self.page.locator("#page-jump").count() == 0:
            self.fail("pagination is missing the page-number input")

        page_input = self.page.locator("#page-jump")
        page_input.fill("8")
        self.page.locator("#jump-page").click()
        page_input.fill("999")
        page_input.press("Enter")
        page_input.fill("0")
        page_input.press("Enter")

        self.assertEqual(self.page.evaluate("window.requestedPages"), [8, 10, 1])

    def test_existing_previous_next_and_page_size_controls_keep_working(self):
        self.page.locator("#prev").click()
        self.page.locator("#next").click()
        self.page.locator("#page-size").select_option("50")

        self.assertEqual(self.page.evaluate("window.requestedPages"), [3, 5])
        self.assertEqual(self.page.evaluate("window.requestedPageSizes"), ["50"])


if __name__ == "__main__":
    unittest.main()
