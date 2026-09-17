from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / '南化建招聘管理系统操作手册.docx'
BLUE = '0B5FCC'
DARK_BLUE = '123A67'
PALE_BLUE = 'EEF5FD'
LIGHT_BLUE = 'F6F9FD'
GRAY = 'D9D9D9'
TEXT = RGBColor(31, 47, 68)
MUTED = RGBColor(92, 108, 128)


def set_cell_shading(cell, fill):
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = tc_pr.find(qn('w:shd'))
    if shd is None:
        shd = OxmlElement('w:shd')
        tc_pr.append(shd)
    shd.set(qn('w:fill'), fill)


def set_cell_margins(cell, top=100, start=120, bottom=100, end=120):
    tc = cell._tc
    tc_pr = tc.get_or_add_tcPr()
    tc_mar = tc_pr.first_child_found_in('w:tcMar')
    if tc_mar is None:
        tc_mar = OxmlElement('w:tcMar')
        tc_pr.append(tc_mar)
    for name, value in [('top', top), ('start', start), ('bottom', bottom), ('end', end)]:
        node = tc_mar.find(qn(f'w:{name}'))
        if node is None:
            node = OxmlElement(f'w:{name}')
            tc_mar.append(node)
        node.set(qn('w:w'), str(value))
        node.set(qn('w:type'), 'dxa')


def set_table_borders(table, color=GRAY, size='6'):
    tbl_pr = table._tbl.tblPr
    borders = tbl_pr.first_child_found_in('w:tblBorders')
    if borders is None:
        borders = OxmlElement('w:tblBorders')
        tbl_pr.append(borders)
    for edge in ('top', 'left', 'bottom', 'right', 'insideH', 'insideV'):
        tag = qn(f'w:{edge}')
        element = borders.find(tag)
        if element is None:
            element = OxmlElement(f'w:{edge}')
            borders.append(element)
        element.set(qn('w:val'), 'single')
        element.set(qn('w:sz'), size)
        element.set(qn('w:space'), '0')
        element.set(qn('w:color'), color)


def set_repeat_table_header(row):
    tr_pr = row._tr.get_or_add_trPr()
    header = OxmlElement('w:tblHeader')
    header.set(qn('w:val'), 'true')
    tr_pr.append(header)


def keep_with_next(paragraph):
    paragraph.paragraph_format.keep_with_next = True


def add_page_number(paragraph):
    paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run = paragraph.add_run('第 ')
    run.font.size = Pt(9)
    fld_begin = OxmlElement('w:fldChar')
    fld_begin.set(qn('w:fldCharType'), 'begin')
    instr = OxmlElement('w:instrText')
    instr.set(qn('xml:space'), 'preserve')
    instr.text = ' PAGE '
    fld_end = OxmlElement('w:fldChar')
    fld_end.set(qn('w:fldCharType'), 'end')
    run._r.append(fld_begin)
    run._r.append(instr)
    run._r.append(fld_end)
    paragraph.add_run(' 页').font.size = Pt(9)


def set_run_font(run, name='Microsoft YaHei', size=None, bold=None, color=None):
    run.font.name = name
    run._element.get_or_add_rPr().rFonts.set(qn('w:eastAsia'), name)
    run._element.get_or_add_rPr().rFonts.set(qn('w:ascii'), name)
    run._element.get_or_add_rPr().rFonts.set(qn('w:hAnsi'), name)
    if size is not None:
        run.font.size = Pt(size)
    if bold is not None:
        run.bold = bold
    if color is not None:
        run.font.color.rgb = color


def add_bullets(doc, items, level=0):
    for item in items:
        p = doc.add_paragraph(style='List Bullet' if level == 0 else 'List Bullet 2')
        p.add_run(item)


def add_steps(doc, items):
    for item in items:
        p = doc.add_paragraph(style='List Number')
        p.add_run(item)


def add_note(doc, label, text):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(5)
    p.paragraph_format.space_after = Pt(8)
    lead = p.add_run(label + '：')
    lead.bold = True
    lead.font.color.rgb = RGBColor(11, 95, 204)
    p.add_run(text)


def add_table(doc, headers, rows, widths=None):
    table = doc.add_table(rows=1, cols=len(headers))
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    set_table_borders(table)
    header = table.rows[0]
    set_repeat_table_header(header)
    for index, text in enumerate(headers):
        cell = header.cells[index]
        set_cell_shading(cell, DARK_BLUE)
        set_cell_margins(cell)
        cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = p.add_run(str(text))
        set_run_font(r, size=9.5, bold=True, color=RGBColor(255, 255, 255))
    for row_index, row_data in enumerate(rows):
        cells = table.add_row().cells
        for index, value in enumerate(row_data):
            cell = cells[index]
            set_cell_margins(cell)
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            if row_index % 2:
                set_cell_shading(cell, LIGHT_BLUE)
            p = cell.paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER if index == 0 and len(headers) > 2 else WD_ALIGN_PARAGRAPH.LEFT
            r = p.add_run(str(value))
            set_run_font(r, size=9.2, color=TEXT)
    if widths:
        for row in table.rows:
            for index, width in enumerate(widths):
                row.cells[index].width = Inches(width)
    doc.add_paragraph().paragraph_format.space_after = Pt(2)
    return table


def add_heading(doc, text, level=1):
    p = doc.add_heading(text, level=level)
    keep_with_next(p)
    return p


def add_chapter(doc, number, title):
    if number > 1:
        doc.add_page_break()
    add_heading(doc, f'{number} {title}', 1)


def configure_document(doc):
    section = doc.sections[0]
    section.page_width = Inches(8.5)
    section.page_height = Inches(11)
    section.top_margin = Inches(0.72)
    section.bottom_margin = Inches(0.7)
    section.left_margin = Inches(0.78)
    section.right_margin = Inches(0.78)
    section.different_first_page_header_footer = True

    styles = doc.styles
    normal = styles['Normal']
    normal.font.name = 'Microsoft YaHei'
    normal._element.rPr.rFonts.set(qn('w:eastAsia'), 'Microsoft YaHei')
    normal.font.size = Pt(10.5)
    normal.font.color.rgb = TEXT
    normal.paragraph_format.space_after = Pt(6)
    normal.paragraph_format.line_spacing = 1.25

    title = styles['Title']
    title.font.name = 'Microsoft YaHei'
    title._element.rPr.rFonts.set(qn('w:eastAsia'), 'Microsoft YaHei')
    title.font.size = Pt(30)
    title.font.bold = True
    title.font.color.rgb = RGBColor(0, 0, 0)

    for style_name, size in [('Heading 1', 19), ('Heading 2', 14), ('Heading 3', 11.5)]:
        style = styles[style_name]
        style.font.name = 'Microsoft YaHei'
        style._element.rPr.rFonts.set(qn('w:eastAsia'), 'Microsoft YaHei')
        style.font.size = Pt(size)
        style.font.bold = True
        style.font.color.rgb = RGBColor(0, 0, 0)
        style.paragraph_format.space_before = Pt(12 if style_name != 'Heading 1' else 4)
        style.paragraph_format.space_after = Pt(7)
        style.paragraph_format.keep_with_next = True

    for style_name in ('List Bullet', 'List Bullet 2', 'List Number'):
        style = styles[style_name]
        style.font.name = 'Microsoft YaHei'
        style._element.rPr.rFonts.set(qn('w:eastAsia'), 'Microsoft YaHei')
        style.font.size = Pt(10.5)
        style.paragraph_format.space_after = Pt(4)
        style.paragraph_format.line_spacing = 1.2

    header = section.header
    hp = header.paragraphs[0]
    hp.alignment = WD_ALIGN_PARAGRAPH.LEFT
    hr = hp.add_run('南化建招聘管理系统操作手册')
    set_run_font(hr, size=9, color=MUTED)
    footer = section.footer
    add_page_number(footer.paragraphs[0])


def cover(doc):
    for _ in range(4):
        doc.add_paragraph()
    title = doc.add_paragraph(style='Title')
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title.add_run('南化建招聘管理系统操作手册')
    subtitle = doc.add_paragraph()
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
    subtitle.paragraph_format.space_before = Pt(14)
    subtitle.paragraph_format.space_after = Pt(34)
    run = subtitle.add_run('管理员与招聘工作人员使用')
    set_run_font(run, size=14, color=MUTED)
    items = [
        ('系统名称', '南化建招聘管理系统'),
        ('文档版本', '1.0'),
        ('适用版本', '2026年9月14日当前版本'),
        ('编制日期', '2026年9月14日'),
    ]
    for left, right in items:
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_after = Pt(7)
        label = p.add_run(left + '　')
        set_run_font(label, size=10.5, bold=True, color=MUTED)
        value = p.add_run(right)
        set_run_font(value, size=10.5, color=TEXT)
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(36)
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run('南京南化建设有限公司')
    set_run_font(r, size=14, bold=True, color=RGBColor(0, 0, 0))
    doc.add_page_break()


def contents(doc):
    add_heading(doc, '使用说明', 1)
    doc.add_paragraph('本手册面向招聘系统管理员和招聘工作人员，说明当前版本的日常操作、部署维护、Dify 简历识别及数据备份方法。系统中的人员资料和附件保存在部署电脑本地数据库中，版本更新前应先备份数据。')
    add_note(doc, '阅读建议', '首次使用请先阅读第1至3章；日常业务按第4至11章操作；部署、更新或排查故障时查阅第12至14章。')
    add_heading(doc, '目录', 1)
    entries = [
        '1 系统概览', '2 启动与访问', '3 登录与账号管理', '4 招聘总览',
        '5 简历收集与批量上传', '6 Dify 简历识别与入库', '7 人才库',
        '8 院校基础库', '9 校园招聘应聘登记', '10 校园招聘面试情况表',
        '11 新员工登记与问题库', '12 通用列表操作', '13 部署更新与数据备份',
        '14 常见问题处理', '附录 A 关键规则速查',
    ]
    for entry in entries:
        p = doc.add_paragraph()
        p.paragraph_format.left_indent = Inches(0.15)
        p.paragraph_format.space_after = Pt(5)
        p.add_run(entry)
    doc.add_page_break()


def chapter_system_overview(doc):
    add_chapter(doc, 1, '系统概览')
    doc.add_paragraph('南化建招聘管理系统用于集中管理简历、人才档案、院校资料、校园招聘应聘记录、面试记录、新员工资料和常见问题。管理端采用浏览器访问，数据保存在运行服务的电脑中。')
    add_heading(doc, '1.1 功能模块', 2)
    add_table(doc, ['模块', '主要用途', '核心结果'], [
        ('招聘总览', '按校园招聘、社会招聘查看数量和最新记录', '快速进入相关模块'),
        ('简历收集', '上传简历、记录来源并调用 Dify 识别', '识别结果核对后进入人才库'),
        ('人才库', '维护人才基本信息及教育、工作、项目经历', '形成统一人才档案'),
        ('院校基础库', '维护学校、地区、层次和就业网资料', '支持院校信息查询与关联'),
        ('应聘登记', '记录校园招聘初筛、附件、签名和招聘信息', '形成应聘登记记录'),
        ('面试情况表', '维护一面、二面、面试结论和个人情况', '形成面试过程记录'),
        ('新员工登记', '收集拟入职人员的完整登记信息', '形成新员工资料'),
        ('问题库', '维护常见问题与通用回答话术', '形成统一答复口径'),
    ], [1.15, 3.55, 1.95])
    add_heading(doc, '1.2 使用角色', 2)
    add_bullets(doc, [
        '固定管理员 admin：可以管理业务数据、创建成员、查看成员并任命或取消其他管理员。',
        '被任命的管理员：可以创建、查看和注销成员，但不能任命或取消管理员。',
        '普通成员：可以新增、查看、编辑和删除业务数据，并使用导入、导出、二维码和识别功能。',
        '外部投递人员：仅能通过公开二维码页面提交简历或登记资料，不能查看管理端数据。',
    ])
    add_heading(doc, '1.3 数据安全原则', 2)
    add_bullets(doc, [
        '人员信息、附件和账号密码哈希均存放在 data 文件夹的 SQLite 数据库中。',
        'Dify API Key 只应保存在服务电脑的 Windows 用户环境变量中，不得写进网页、文档或聊天记录。',
        '当前 Dify API 使用 HTTP，简历和密钥会以明文传输，只应在受控网络中使用。',
        '更新程序前先停止服务并备份整个 data 文件夹。',
    ])


def chapter_start_access(doc):
    add_chapter(doc, 2, '启动与访问')
    add_heading(doc, '2.1 启动系统', 2)
    add_steps(doc, [
        '打开系统文件夹，确认其中包含 start.bat、server.py、web、features 和 data。',
        '双击 start.bat。启动窗口会显示本机访问地址和局域网访问地址。',
        '保持启动窗口打开。关闭该窗口会停止系统服务。',
        '在服务电脑浏览器访问 http://localhost:8116。',
    ])
    add_note(doc, '首次部署', '新电脑需安装 Python 3.10 或以上版本，并执行 python -m pip install --target .runtime -r requirements.txt，或复制兼容的 .runtime 文件夹。')
    add_heading(doc, '2.2 局域网访问', 2)
    doc.add_paragraph('start.bat 不预设固定 IP。系统启动时自动识别运行电脑当前默认网络出口的 IPv4 地址。其他电脑或手机与服务电脑处于同一局域网时，可访问 http://服务器IP:8116。')
    add_table(doc, ['用途', '地址示例', '说明'], [
        ('管理端', 'http://服务器IP:8116', '需要登录'),
        ('校园招聘应聘登记', 'http://服务器IP:8116/apply', '公开填写入口'),
        ('新员工登记', 'http://服务器IP:8116/onboard', '公开填写入口'),
        ('简历投递', '二维码生成的 /resume-submit 地址', '招聘类型由二维码入口确定'),
    ], [1.45, 2.85, 2.35])
    add_heading(doc, '2.3 防火墙说明', 2)
    doc.add_paragraph('只在服务电脑本机使用时，可以不开放防火墙。需要让同一局域网内的其他电脑或手机访问时，Windows 防火墙必须允许 Python 或 TCP 8116 端口入站。建议只对专用网络和本地子网开放。')
    add_note(doc, '固定地址', '如需长期使用同一地址，应在路由器或网络管理设备中固定服务电脑的局域网 IP。IP 或端口变化后，应重新生成二维码。')


def chapter_accounts(doc):
    add_chapter(doc, 3, '登录与账号管理')
    add_heading(doc, '3.1 管理员首次登录', 2)
    add_steps(doc, [
        '首次启动后，打开 data 文件夹中的 initial-password.txt 查看初始管理员密码。',
        '使用账号 admin 和初始密码登录。',
        '登录后点击右上角“修改密码”，设置新密码。',
        '密码修改成功后，初始密码文件会自动删除，原有登录会话失效。',
    ])
    add_heading(doc, '3.2 创建成员', 2)
    add_steps(doc, [
        '点击右上角圆形账号按钮，进入账号菜单。',
        '管理员选择“创建成员”。',
        '填写成员账号和初始密码；昵称与电话号码可以暂不填写。',
        '点击“创建成员”，将账号和初始密码安全交给对应人员。',
    ])
    add_note(doc, '账号要求', '成员账号使用3至32位字母、数字、下划线或短横线；初始密码为10至128位。昵称最多30个字符，未填写时显示账号名。')
    add_heading(doc, '3.3 账号菜单', 2)
    add_bullets(doc, [
        '编辑个人资料：补充或修改昵称和电话号码。',
        '修改密码：修改当前登录账号密码。',
        '查看成员或创建成员：按当前账号权限显示。',
        '重置成员密码：仅主管理员可用，无需成员原密码；重置后成员的现有登录会话立即失效。',
        '切换账号：退出当前账号后登录另一账号。',
        '退出登录：清除当前登录状态并返回登录页。',
    ])


def chapter_overview(doc):
    add_chapter(doc, 4, '招聘总览')
    doc.add_paragraph('招聘总览按校园招聘和社会招聘分别显示简历、人才、院校、应聘和面试数据。新员工登记单独统计。页面右上角显示当前日期，并提供“新增”按钮。')
    add_heading(doc, '4.1 查看统计', 2)
    add_steps(doc, [
        '点击左侧“招聘总览”。',
        '查看校园招聘、社会招聘和新员工登记区域的数量卡片。',
        '点击任一卡片进入对应业务页面。',
        '在“最新人才登记”中查看近期录入的人才。',
    ])
    add_heading(doc, '4.2 快速新增人才', 2)
    add_steps(doc, [
        '点击总览右上角“新增”。',
        '填写人才基本资料和经历信息。',
        '核对招聘类型、渠道和岗位后保存。',
    ])


def chapter_resume_collection(doc):
    add_chapter(doc, 5, '简历收集与批量上传')
    add_heading(doc, '5.1 页面内容', 2)
    doc.add_paragraph('简历收集页集中保存文档和图片简历。每条记录显示档案编号、处理状态、简历名称、应聘岗位、招聘类型、招聘渠道、附件、创建人和上传时间。上传时间即创建时间，由系统自动生成。')
    add_heading(doc, '5.2 单份上传', 2)
    add_steps(doc, [
        '点击“新增”。',
        '选择招聘类型和招聘渠道。选择“其他”渠道时填写渠道详情。',
        '选择应聘岗位。选择“其它”时填写实际岗位名称。',
        '选择简历文件并保存。系统自动记录当前登录人为创建人。',
    ])
    add_heading(doc, '5.3 批量上传', 2)
    add_steps(doc, [
        '点击“批量导入简历”。',
        '先选择本批简历统一使用的招聘类型和招聘渠道。',
        '点击“增加文件”，可多次添加文件；选择窗口也支持一次选择多份。',
        '核对文件清单后提交。系统逐份创建简历记录。',
    ])
    add_note(doc, '外链状态', '免登录批量导入外链功能当前暂停。批量导入需在登录管理系统后操作。')
    add_heading(doc, '5.4 支持的文件类型', 2)
    add_table(doc, ['类别', '扩展名'], [
        ('文档', 'TXT、MD、MDX、MARKDOWN、PDF、HTML、XLSX、XLS、DOC、DOCX、CSV、EML、MSG、PPTX、PPT、XML、EPUB'),
        ('图片', 'JPG、JPEG、PNG、GIF、WEBP、SVG'),
    ], [1.15, 5.5])
    doc.add_paragraph('每份文件最大50MB。系统会检查扩展名和基础文件内容。上传相同文件时，系统根据文件指纹阻止重复保存。')
    add_heading(doc, '5.5 文件名识别岗位', 2)
    doc.add_paragraph('系统会从简历文件名中尝试识别应聘岗位并填入记录。例如文件名包含“电气工程师”时，岗位可自动选择“电气工程师”。文件名信息不明确时保持为空，需人工选择。选择“其它”后填写的实际岗位不会在列表主页单独显示。')
    add_heading(doc, '5.6 筛选简历', 2)
    add_steps(doc, [
        '在搜索框右侧点击“筛选”。',
        '按上传时间、招聘类型或招聘渠道设置条件。',
        '应用筛选后查看结果；需要恢复全部记录时清除筛选。',
    ])


def chapter_dify(doc):
    add_chapter(doc, 6, 'Dify 简历识别与入库')
    add_heading(doc, '6.1 首次配置', 2)
    add_steps(doc, [
        '双击“配置Dify.bat”。',
        '在隐藏输入框中粘贴工作流 API Key 并确认。',
        '配置完成后可以关闭配置窗口。',
        '关闭正在运行的旧服务窗口，再双击 start.bat 重新启动系统。',
    ])
    add_table(doc, ['配置项', '当前默认值或说明'], [
        ('API 地址', 'http://biaozhun.njncc.com/v1'),
        ('公开工作流', 'http://biaozhun.njncc.com/workflow/e3JaA7Tg8GrWKJi5'),
        ('简历变量', 'resume_file'),
        ('招聘类型变量', 'recruitment_type'),
        ('招聘渠道变量', 'source_channel'),
        ('岗位变量', 'position_name'),
    ], [1.8, 4.85])
    add_note(doc, '安全提示', '不要在手册、前端代码或工作流公开网址中写入 API Key。当前 API 使用 HTTP，只应在受控网络中使用。')
    add_heading(doc, '6.2 单条识别', 2)
    add_steps(doc, [
        '在简历收集列表找到状态为“待识别”或“失败”的记录。',
        '点击该行“识别”。系统自动上传附件并运行 Dify 工作流。',
        '识别成功后，系统自动打开人才核对弹窗。',
        '核对姓名、电话、学历、院校、专业、岗位和经历信息。',
        '确认无误后保存，记录状态变为“已入库”。',
    ])
    add_heading(doc, '6.3 批量识别', 2)
    add_steps(doc, [
        '勾选一条或多条待识别或失败记录。',
        '点击“识别（数量）”。',
        '保持页面打开，系统按顺序处理。当前一次只运行一个识别请求。',
        '逐条核对识别结果并保存入库。',
    ])
    add_heading(doc, '6.4 识别规则', 2)
    add_bullets(doc, [
        '教育经历按毕业时间倒序；无毕业时间时参考入学时间。',
        '工作经历和项目经历按开始时间倒序；无开始时间时参考结束时间。',
        '完全没有有效时间的记录排在最后，并保持原简历顺序。',
        '入学时间只有年份时默认补为9月；毕业时间只有年份时默认补为7月。',
        '项目经历只保留给社会招聘人才；校园招聘识别结果不保存项目经历。',
    ])
    add_heading(doc, '6.5 失败和重新识别', 2)
    doc.add_paragraph('状态为“失败”的记录可以再次点击“识别”。人才库中的对应人才被删除后，原简历记录会恢复为待识别并释放旧的入库标记，可以重新识别录入。已入库且人才仍存在时，系统不会重复创建人才。')


def chapter_candidates(doc):
    add_chapter(doc, 7, '人才库')
    add_heading(doc, '7.1 新增人才', 2)
    add_steps(doc, [
        '进入“人才库”，点击“新增”。',
        '选择招聘类型。招聘渠道会根据招聘类型显示可用选项。',
        '填写姓名、联系方式、毕业院校、学历和专业等必填信息。',
        '按顺序维护教育经历、工作经历和项目经历，再上传简历附件。',
        '核对投递时间和投递岗位后保存。',
    ])
    add_heading(doc, '7.2 档案编号规则', 2)
    doc.add_paragraph('档案编号由系统保存时自动生成，不能手工修改。格式为招聘类型代码、录入年月日和当日顺序号。社会招聘代码为01，校园招聘代码为02。')
    add_table(doc, ['示例', '含义'], [
        ('0120260914001', '2026年9月14日录入的第1名社会招聘人才'),
        ('0120260914002', '2026年9月14日录入的第2名社会招聘人才'),
        ('0220260914001', '2026年9月14日录入的第1名校园招聘人才'),
    ], [2.25, 4.4])
    add_heading(doc, '7.3 教育经历', 2)
    add_bullets(doc, [
        '第一行填写学历、院校和专业；第二行填写入学时间和毕业时间。',
        '可以添加多条教育经历，每条记录分别保存。',
        '毕业时间自动取最高学历教育经历的毕业时间。人才弹窗不单独显示毕业时间字段。',
        '校园招聘按最高学历毕业年份计算并在人才库列表显示应届届别；社会招聘不显示应届。',
    ])
    add_heading(doc, '7.4 工作经历和项目经历', 2)
    add_table(doc, ['经历类型', '适用范围', '填写规则'], [
        ('工作经历', '校园招聘和社会招聘通用', '工作单位必填；岗位可不填；起止时间和工作描述按实际填写'),
        ('项目经历', '仅社会招聘', '项目名称和开始时间必填；担任角色可不填；结束时间留空表示至今'),
    ], [1.25, 1.75, 3.65])
    doc.add_paragraph('人才弹窗中的顺序为教育经历、工作经历、项目经历、简历附件。招聘类型改为校园招聘并保存时，已有项目经历会自动删除。')
    add_heading(doc, '7.5 招聘渠道和岗位', 2)
    add_table(doc, ['字段', '选项'], [
        ('招聘类型', '校园招聘、社会招聘'),
        ('校园招聘渠道', '校园线下、校园平台、智联招聘'),
        ('社会招聘渠道', 'boss直聘、智联招聘、化工英才网、其他'),
        ('投递岗位', '机械工程师、电气工程师、安全工程师、土建工程师、管道工程师、设备工程师、数据分析师、软件工程师、财务专员、其它'),
    ], [1.55, 5.1])
    add_note(doc, '其它选项', '选择“其他”招聘渠道或“其它”岗位后，必须在出现的输入框中填写实际内容。详细内容保存在记录中，但不在主页列表单独显示。')
    add_heading(doc, '7.6 政治面貌', 2)
    doc.add_paragraph('政治面貌采用下拉选择：群众、共青团员、中共预备党员、中共党员。该字段可以留空。')


def chapter_schools(doc):
    add_chapter(doc, 8, '院校基础库')
    add_heading(doc, '8.1 新增院校', 2)
    add_steps(doc, [
        '进入“院校基础库”，点击“新增”。',
        '填写学校名称、所在地区、所在省和所在市。',
        '选择办学层次、办学形式以及985、211、双一流标记。',
        '按需填写业务开发领导、就业网账号、密码、网址和院校排名。',
        '保存后，系统根据省、市自动生成“所在省市”。',
    ])
    add_heading(doc, '8.2 省市联动', 2)
    doc.add_paragraph('选择省份后，所在市下拉框只显示该省可选城市。切换省份会清空原城市。系统拒绝保存省市不匹配的数据。直辖市、香港和澳门按对应同名城市处理。')
    add_heading(doc, '8.3 就业网资料', 2)
    add_bullets(doc, [
        '就业网网址应填写完整的 HTTP 或 HTTPS 地址。',
        '就业网密码在编辑表单中默认隐藏，需要时点击“显示”。',
        '就业网密码不参与搜索，也不会导出到 Excel。',
        '只有授权人员可以查看和修改院校就业网账号及密码。',
    ])


def chapter_applications(doc):
    add_chapter(doc, 9, '校园招聘应聘登记')
    add_heading(doc, '9.1 管理端新增', 2)
    add_steps(doc, [
        '进入“校园招聘应聘登记”，点击“新增”。',
        '优先填写联系电话。系统按相同电话查找人才库并带入已有资料。',
        '依次填写姓名、身份证、教育经历、初筛情况、语言能力和招聘信息。',
        '上传成绩单、证书、简历或手写本人签名。',
        '选择数据状态并保存。',
    ])
    add_heading(doc, '9.2 身份证自动填写', 2)
    doc.add_paragraph('填写有效的18位身份证号码后，系统自动提取出生日期、计算年龄并填写性别。号码完整且校验通过时，出生日期和性别会锁定；清空身份证后可以手工填写。服务端保存时再次校验。')
    add_heading(doc, '9.3 电话匹配人才', 2)
    add_bullets(doc, [
        '电话匹配到唯一人才时，系统带入姓名、院校、专业、学历、教育经历和简历。',
        '普通字段修改只影响本次应聘登记快照，不反向修改人才库。',
        '教育经历保存时会同步到已关联的人才档案。',
        '电话改为未匹配人员时，系统清除原人才关联的简历和教育经历带入数据。',
    ])
    add_heading(doc, '9.4 公开登记页面', 2)
    doc.add_paragraph('将 http://服务器IP:8116/apply 或对应二维码提供给应聘人员。提交成功后，系统在同一事务中创建人才档案和应聘登记。相同电话重复提交会被拦截，需由管理人员修改已有资料。')
    add_heading(doc, '9.5 附件和签名', 2)
    add_table(doc, ['字段', '支持格式', '说明'], [
        ('成绩单', 'PDF、DOC、DOCX、JPG、PNG', '每个字段一份文件，最大50MB'),
        ('证书附件', 'PDF、DOC、DOCX、JPG、PNG', '可保留、替换或移除'),
        ('简历', 'PDF、DOC、DOCX', '匹配人才时可复用已有附件'),
        ('本人签名', 'JPG、PNG或手写', '手写签名保存为PNG附件'),
    ], [1.25, 2.25, 3.15])


def chapter_interviews(doc):
    add_chapter(doc, 10, '校园招聘面试情况表')
    add_heading(doc, '10.1 新增面试记录', 2)
    add_steps(doc, [
        '进入“校园招聘面试情况表”，点击“新增”。',
        '优先填写身份证。系统按相同身份证从应聘登记中带入最近一份资料。',
        '填写是否一面、流程状态、面试时间和岗位。',
        '补充性格、家庭情况、在校职务、实习情况和可接受项目地。',
        '填写一面、二面说明和面试结果后保存。',
    ])
    add_heading(doc, '10.2 资料带入规则', 2)
    add_bullets(doc, [
        '系统只按身份证匹配应聘登记，不按手机号直接读取人才库。',
        '同一身份证有多条应聘登记时，使用编号最新的一条。',
        '匹配成功时可复用成绩单、证书和简历，也可上传替换。',
        '面试记录的状态、结果和说明不会反向修改人才库或应聘登记。',
    ])
    add_heading(doc, '10.3 状态和结果', 2)
    add_table(doc, ['字段', '可选值'], [
        ('是否一面', '同意、拒绝、不合适'),
        ('流程状态', '草稿、已生效、进行中、已取消'),
        ('是否通过一面', '是、否'),
        ('面试结果', 'pass、发offer'),
    ], [1.8, 4.85])
    add_note(doc, '时间精度', '面试时间保存到分钟；创建日期由系统自动记录到秒。')


def chapter_employee_questions(doc):
    add_chapter(doc, 11, '新员工登记与问题库')
    add_heading(doc, '11.1 新员工信息登记', 2)
    add_steps(doc, [
        '进入“新员工信息登记表”，点击“新增”，或向新员工提供 /onboard 公开登记入口。',
        '填写姓名、身份证、联系方式、院校、学历和专业。',
        '填写身高、体重、鞋码、岗位、家庭住址、入学形式和招聘途径。',
        '核对后保存。身份证通过校验时，出生日期和性别自动填写。',
    ])
    add_heading(doc, '11.2 应聘人员问题库', 2)
    add_steps(doc, [
        '进入“应聘人员问题库”，点击“新增”。',
        '填写问题和通用回答话术。',
        '保存后可通过搜索快速查找统一答复。',
        '需要批量维护时，可使用 Excel 导入或选择记录后导出。',
    ])


def chapter_common_operations(doc):
    add_chapter(doc, 12, '通用列表操作')
    add_heading(doc, '12.1 搜索', 2)
    doc.add_paragraph('各业务页面的搜索框支持姓名、院校、岗位等关键词；存在档案编号的页面同时支持搜索完整或部分档案编号。输入内容后列表即时更新。')
    add_heading(doc, '12.2 分页', 2)
    add_bullets(doc, [
        '每页条数可选择10、20、50或100。',
        '页码下方显示总记录数和当前页数。',
        '列表编号连续计算，下一页从上一页末尾继续编号。',
        '切换页面不会自动清除跨页勾选；切换业务模块或刷新模块会清除勾选。',
    ])
    add_heading(doc, '12.3 查看和编辑', 2)
    add_steps(doc, [
        '在记录操作栏点击“查看 / 编辑”。',
        '修改所需字段。弹窗关闭按钮位于白色内容框外的右上角，滚动到任意位置均可关闭。',
        '点击“保存”。保存失败时，根据弹窗中的提示修改后再次提交。',
    ])
    add_heading(doc, '12.4 批量删除', 2)
    add_steps(doc, [
        '勾选需要删除的单条或多条记录，可跨页选择。',
        '点击“删除所选（数量）”。',
        '在确认窗口核对实际记录，再确认删除。',
    ])
    add_note(doc, '关联限制', '批量删除采用整批事务。任何记录被其他业务数据引用、已不存在或不允许删除时，整批回滚，不会只删除其中一部分。删除人才后，未被其他记录引用的普通附件会清理；简历收集中的源文件会保留并恢复待识别。')
    add_heading(doc, '12.5 Excel 导入', 2)
    add_steps(doc, [
        '点击“导入 Excel”。',
        '下载模板，或选择已有 XLSX、XLS 文件。',
        '选择工作表并核对系统识别的表头和字段映射。',
        '查看前20条预览及错误提示。',
        '确认后提交。整批校验通过才会写入数据库。',
    ])
    add_note(doc, '导入限制', '文件最大8MB，每次最多1000条、150列。简历收集页不使用 Excel 导入，而使用“批量导入简历”。')
    add_heading(doc, '12.6 Excel 导出', 2)
    add_steps(doc, [
        '先勾选需要导出的记录。未勾选时导出按钮不可用。',
        '点击“导出 Excel”。系统只导出已选择的数据，不导出全部记录。',
        '打开工作簿后，可点击附件列中的超链接查看附件。',
    ])
    add_note(doc, '附件链接', '查看导出附件时，系统服务必须正在运行，访问地址可用，并且浏览器已登录管理系统。附件不会直接嵌入 Excel。简历收集页面不提供导出功能。')
    add_heading(doc, '12.7 二维码', 2)
    add_bullets(doc, [
        '单条记录可在操作栏点击“二维码”。',
        '批量打印时先勾选记录，再点击“打印二维码”。每次最多100条。',
        '二维码卡片可下载图片或通过浏览器打印为 PDF。',
        '校园招聘简历投递二维码上方显示“校园招聘简历投递”，卡片保留公司名称，可直接用于招聘传单。',
        '管理记录二维码只包含记录链接，不包含人才资料或就业网密码；扫码后仍需登录。',
    ])


def chapter_deployment(doc):
    add_chapter(doc, 13, '部署更新与数据备份')
    add_heading(doc, '13.1 部署到另一台电脑', 2)
    add_steps(doc, [
        '在原电脑关闭 start.bat 运行窗口。',
        '复制完整系统文件夹到目标电脑。若要保留原数据，必须包含完整 data 文件夹。',
        '在目标电脑安装 Python 和依赖，或复制兼容的 .runtime 文件夹。',
        '双击 start.bat，记录窗口显示的局域网地址。',
        '在目标电脑本机测试 localhost:8116，再从同一局域网的另一台设备测试服务器IP:8116。',
        '重新配置 Dify API Key。Windows 用户环境变量不会随项目文件夹复制。',
        '需要局域网访问时配置防火墙，并重新生成二维码。',
    ])
    add_heading(doc, '13.2 数据备份', 2)
    add_steps(doc, [
        '通知使用人员暂停操作。',
        '关闭 start.bat 窗口，确认服务已经停止。',
        '复制整个 data 文件夹到备份位置，并以日期命名。',
        '确认备份中包含 recruitment.db；如存在 db-wal 或 db-shm 文件也一并保留。',
        '重新启动系统并确认可以登录。',
    ])
    add_note(doc, '重要', '不要在服务运行时只复制 recruitment.db。数据库使用 WAL 模式，未合并的数据可能仍在 db-wal 文件中。备份包含人员资料、附件和密码哈希，应限制访问权限。')
    add_heading(doc, '13.3 更新系统版本', 2)
    add_steps(doc, [
        '停止旧版本服务并备份整个旧系统文件夹，至少备份完整 data 文件夹。',
        '保留旧版本的 data 文件夹，不要用新版空 data 覆盖。',
        '更新 server.py、web、features、scripts、requirements.txt、start.bat 等程序文件。',
        '将旧 data 文件夹放在新版本项目根目录中。',
        '启动新版本。系统会自动执行必要的数据迁移，并在 data 中生成迁移前备份。',
        '检查简历、人才、院校、应聘、面试和新员工记录数量。',
    ])
    add_heading(doc, '13.4 数据恢复', 2)
    add_steps(doc, [
        '停止系统服务。',
        '将当前 data 文件夹改名保存，避免覆盖后无法回退。',
        '把已确认完整的备份 data 文件夹复制到项目根目录。',
        '启动系统并登录检查数据。',
    ])
    add_note(doc, '空数据原因', '新系统显示空白时，通常是程序读取了新建的 data/recruitment.db，而不是旧数据库。先查找旧系统文件夹或备份，不要继续覆盖文件。')


def chapter_troubleshooting(doc):
    add_chapter(doc, 14, '常见问题处理')
    add_table(doc, ['现象', '检查方法', '处理建议'], [
        ('双击 start.bat 无法启动', '查看窗口中的错误；确认 Python 可用及8116端口未被占用', '安装 Python 3.10以上和依赖；关闭占用端口的旧服务'),
        ('本机可以访问，其他设备打不开', '确认设备在同一网络；检查服务地址和防火墙', '使用服务器实际IPv4；允许专用网络TCP 8116入站'),
        ('登录密码不正确', '确认账号和密码；首次启动检查 initial-password.txt', '管理员登录后重置成员；不要删除数据库重建账号'),
        ('更新后旧数据不见了', '检查当前项目 data/recruitment.db 与旧目录或备份', '停止服务，用完整旧 data 文件夹恢复'),
        ('Dify 连接失败或超时', '确认 API 地址、Key、网络和工作流是否发布', '重新运行配置Dify.bat并重启服务；稍后重试'),
        ('识别结果字段不正确', '检查简历原文、招聘类型、渠道和岗位；查看Dify输出', '在核对弹窗人工修正后再保存；必要时调整工作流'),
        ('失败记录不能入库', '检查人才必填项、电话重复、经历必填项和日期先后', '按错误提示补充或修改；失败记录可再次识别'),
        ('附件无法打开', '确认服务运行、链接地址可访问且已登录', '重新登录管理端；从原记录中点击附件验证'),
        ('无法删除记录', '检查记录是否被应聘、面试、入职等数据引用', '先处理关联记录，再删除主记录'),
        ('二维码扫码后打不开', '检查二维码中的IP、端口和当前网络', '固定服务电脑IP并重新生成二维码'),
    ], [1.5, 2.55, 2.6])
    add_heading(doc, '14.1 排查顺序', 2)
    add_steps(doc, [
        '记录出现问题的页面、操作步骤和错误提示。',
        '确认 start.bat 窗口仍在运行。',
        '在服务电脑访问 localhost:8116，判断是服务问题还是局域网问题。',
        '检查 data 文件夹和数据库备份，不要直接删除数据库。',
        '涉及 Dify 时，分别检查系统、Dify API 地址、密钥和工作流运行记录。',
    ])


def appendix(doc):
    doc.add_page_break()
    add_heading(doc, '附录 A 关键规则速查', 1)
    add_table(doc, ['事项', '规则'], [
        ('页面条数', '10、20、50、100'),
        ('政治面貌', '群众、共青团员、中共预备党员、中共党员'),
        ('岗位', '机械、电气、安全、土建、管道、设备、数据分析、软件、财务、其它'),
        ('社会招聘编号', '01 + 年月日 + 三位顺序号'),
        ('校园招聘编号', '02 + 年月日 + 三位顺序号'),
        ('入学时间缺月份', '默认9月'),
        ('毕业时间缺月份', '默认7月'),
        ('人才应届显示', '仅校园招聘；按最高学历毕业年份计算'),
        ('工作经历', '校园招聘和社会招聘通用；岗位可不填'),
        ('项目经历', '仅社会招聘；担任角色可不填'),
        ('简历收集导入', '批量上传文档或图片，不使用Excel'),
        ('简历收集导出', '不提供导出'),
        ('其他页面导出', '仅导出已选择记录；附件为超链接'),
        ('公开批量导入外链', '当前暂停'),
        ('数据库位置', '项目目录 data/recruitment.db'),
        ('Dify配置', '配置Dify.bat；配置后重启服务'),
    ], [2.15, 4.5])
    add_heading(doc, '附录 B 日常操作检查清单', 1)
    add_bullets(doc, [
        '每天开始工作时确认服务窗口正常运行，管理端可以登录。',
        '上传简历时核对招聘类型、招聘渠道和岗位。',
        '识别入库前核对姓名、电话、院校、学历、专业和经历。',
        '批量删除和导出前核对勾选数量。',
        '系统更新、迁移电脑或恢复数据前先停止服务并备份整个 data 文件夹。',
        '定期验证备份可以打开，并限制备份文件访问权限。',
    ])
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(24)
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run('手册结束')
    set_run_font(r, size=11, bold=True, color=MUTED)


def build():
    doc = Document()
    configure_document(doc)
    cover(doc)
    contents(doc)
    chapter_system_overview(doc)
    chapter_start_access(doc)
    chapter_accounts(doc)
    chapter_overview(doc)
    chapter_resume_collection(doc)
    chapter_dify(doc)
    chapter_candidates(doc)
    chapter_schools(doc)
    chapter_applications(doc)
    chapter_interviews(doc)
    chapter_employee_questions(doc)
    chapter_common_operations(doc)
    chapter_deployment(doc)
    chapter_troubleshooting(doc)
    appendix(doc)
    for paragraph in doc.paragraphs:
        for run in paragraph.runs:
            if run.font.name is None:
                set_run_font(run)
    doc.core_properties.title = '南化建招聘管理系统操作手册'
    doc.core_properties.subject = '管理员与招聘工作人员操作指南'
    doc.core_properties.author = '南京南化建设有限公司'
    doc.core_properties.keywords = '招聘管理 简历 人才库 Dify 操作手册'
    doc.save(OUTPUT)
    print(OUTPUT)


if __name__ == '__main__':
    build()
