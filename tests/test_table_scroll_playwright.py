from pathlib import Path
import unittest

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]


class TableScrollLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def setUp(self):
        self.page = self.browser.new_page(viewport={"width": 1440, "height": 900})
        rows = "".join(
            f"<tr><td>{index}</td><td>测试数据 {index}</td><td>校园招聘</td></tr>"
            for index in range(1, 41)
        )
        self.page.set_content(
            f"""
            <div class="layout">
              <div class="workspace">
                <main>
                  <div class="page-title"><h1>人才库</h1></div>
                  <section class="panel records">
                    <div class="toolbar"><input type="search" aria-label="搜索记录"></div>
                    <div id="record-table">
                      <div class="table-wrap">
                        <table>
                          <thead><tr><th>编号</th><th>姓名</th><th>招聘类型</th></tr></thead>
                          <tbody>{rows}</tbody>
                        </table>
                      </div>
                      <div class="pagination"><span>共 40 条</span></div>
                    </div>
                  </section>
                  <section class="panel overview-table">
                    <div class="panel-head"><h2>最新人才登记</h2></div>
                    <div class="table-wrap">
                      <table>
                        <thead><tr><th>编号</th><th>姓名</th><th>招聘类型</th></tr></thead>
                        <tbody>{rows}</tbody>
                      </table>
                    </div>
                  </section>
                  <div style="height:900px" aria-hidden="true"></div>
                </main>
              </div>
            </div>
            """
        )
        self.page.add_style_tag(path=str(ROOT / "web" / "style.css"))
        self.page.add_style_tag(path=str(ROOT / "web" / "corporate-theme.css"))

    def tearDown(self):
        self.page.close()

    def test_data_rows_scroll_inside_the_still_scrollable_page(self):
        metrics = self.page.evaluate(
            """
            () => {
              const wrapper = document.querySelector('.records #record-table .table-wrap');
              const style = getComputedStyle(wrapper);
              return {
                pageCanScroll: document.documentElement.scrollHeight > window.innerHeight,
                overflowY: style.overflowY,
                tableCanScroll: wrapper.scrollHeight > wrapper.clientHeight,
              };
            }
            """
        )
        self.assertTrue(metrics["pageCanScroll"])
        self.assertIn(metrics["overflowY"], ("auto", "scroll"))
        self.assertTrue(metrics["tableCanScroll"])

    def test_table_header_stays_visible_while_rows_scroll(self):
        header_style = self.page.locator(".records #record-table thead th").first.evaluate(
            "element => getComputedStyle(element).position"
        )
        self.assertEqual(header_style, "sticky")

    def test_overview_data_table_also_scrolls_independently(self):
        metrics = self.page.locator(".overview-table .table-wrap").evaluate(
            """
            wrapper => ({
              overflowY: getComputedStyle(wrapper).overflowY,
              tableCanScroll: wrapper.scrollHeight > wrapper.clientHeight,
              headerPosition: getComputedStyle(wrapper.querySelector('thead th')).position,
            })
            """
        )
        self.assertIn(metrics["overflowY"], ("auto", "scroll"))
        self.assertTrue(metrics["tableCanScroll"])
        self.assertEqual(metrics["headerPosition"], "sticky")

    def test_pagination_remains_outside_the_table_scroller(self):
        pagination_is_outside = self.page.evaluate(
            """
            () => {
              const wrapper = document.querySelector('.records #record-table .table-wrap');
              const pagination = document.querySelector('.records #record-table .pagination');
              return !wrapper.contains(pagination) && wrapper.compareDocumentPosition(pagination) & Node.DOCUMENT_POSITION_FOLLOWING;
            }
            """
        )
        self.assertTrue(pagination_is_outside)


if __name__ == "__main__":
    unittest.main()
