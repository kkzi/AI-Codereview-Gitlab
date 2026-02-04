# -*- coding: utf-8 -*-
import math
from pathlib import Path

import streamlit as st

# 设置Streamlit主题 - 必须是第一个st命令
st.set_page_config(layout="wide", page_title="AI代码审查平台", page_icon="🤖", initial_sidebar_state="expanded")

import datetime
import os
import hashlib
import hmac
import base64
import time
import pandas as pd
try:
    from dotenv import load_dotenv
    load_dotenv("conf/.env")
except ImportError:
    print("Warning: python-dotenv not found, using default environment variables")
    # Set default values if dotenv is not available
    import os
    if not os.getenv("DASHBOARD_USER"):
        os.environ["DASHBOARD_USER"] = "admin"
    if not os.getenv("DASHBOARD_PASSWORD"):
        os.environ["DASHBOARD_PASSWORD"] = "admin"

from biz.service.review_service import ReviewService

try:
    from streamlit_cookies_manager import CookieManager
except ImportError:
    print("Warning: streamlit-cookies-manager not found, using simple cookie management")
    # Simple cookie manager fallback
    class SimpleCookieManager:
        def __init__(self):
            pass
        def ready(self):
            return True
        def get(self, key):
            return None
        def __contains__(self, key):
            return False
        def __setitem__(self, key, value):
            pass
        def __delitem__(self, key):
            pass
        def save(self):
            pass

    CookieManager = SimpleCookieManager

# 从环境变量中读取用户名和密码
DASHBOARD_USER = os.getenv("DASHBOARD_USER", "admin")
DASHBOARD_PASSWORD = os.getenv("DASHBOARD_PASSWORD", "admin")
USER_CREDENTIALS = {
    DASHBOARD_USER: DASHBOARD_PASSWORD
}

# 用于生成和验证token的密钥
SECRET_KEY = os.getenv("DASHBOARD_SECRET_KEY", "fac8cf149bdd616c07c1a675c4571ccacc40d7f7fe16914cfe0f9f9d966bb773")

# 初始化cookie管理器
cookies = CookieManager()


def generate_token(username):
    """生成包含时间戳的认证token"""
    timestamp = str(int(time.time()))
    message = f"{username}:{timestamp}"

    # 使用HMAC-SHA256生成签名
    signature = hmac.new(
        SECRET_KEY.encode(),
        message.encode(),
        hashlib.sha256
    ).digest()

    # 将消息和签名编码为base64
    token = base64.b64encode(f"{message}:{base64.b64encode(signature).decode()}".encode()).decode()
    return token


def verify_token(token):
    """验证token的有效性并提取用户名"""
    try:
        # 解码token
        decoded = base64.b64decode(token.encode()).decode()
        message, signature = decoded.rsplit(":", 1)
        username, timestamp = message.split(":", 1)

        # 验证签名
        expected_signature = hmac.new(
            SECRET_KEY.encode(),
            message.encode(),
            hashlib.sha256
        ).digest()

        actual_signature = base64.b64decode(signature)

        if not hmac.compare_digest(expected_signature, actual_signature):
            return None

        # 检查token是否过期（30天）
        if int(time.time()) - int(timestamp) > 30 * 24 * 60 * 60:
            return None

        return username
    except:
        return None


# 检查登录状态
def check_login_status():
    if not cookies.ready():
        st.stop()

    if 'login_status' not in st.session_state:
        st.session_state['login_status'] = False

    # 尝试从cookie获取token
    auth_token = cookies.get('auth_token')
    if auth_token:
        username = verify_token(auth_token)
        if username and username in USER_CREDENTIALS:
            st.session_state['login_status'] = True
            st.session_state['username'] = username
            st.session_state['saved_username'] = username

    return st.session_state['login_status']


# 设置登录状态
def set_login_status(username, remember):
    st.session_state['login_status'] = True
    st.session_state['username'] = username
    st.session_state['saved_username'] = username if remember else ''

    if remember:
        # 生成并保存token到cookie
        auth_token = generate_token(username)
        cookies['auth_token'] = auth_token
    else:
        # 如果不记住登录状态，清除cookie
        if 'auth_token' in cookies:
            del cookies['auth_token']
    cookies.save()


# 获取保存的用户名
def get_saved_credentials():
    auth_token = cookies.get('auth_token')
    if auth_token:
        username = verify_token(auth_token)
        if username:
            return username, ''
    return st.session_state.get('saved_username', ''), ''


# 登录验证函数
def authenticate(username, password, remember_password=False):
    if username in USER_CREDENTIALS and USER_CREDENTIALS[username] == password:
        set_login_status(username, remember_password)
        return True
    return False


def format_delta(row):
    if not math.isnan(row['additions']) and not math.isnan(row['deletions']):
        return f"+{int(row['additions'])}\n-{int(row['deletions'])}"
    else:
        return ""


def format_status(status):
    if status == "success":
        return "√"
    elif status == "failed":
        return "×"
    return status


# 获取数据函数
def get_data(service_func, authors=None, project_names=None, updated_at_gte=None, updated_at_lte=None, columns=None):
    df = service_func(authors=authors, project_names=project_names, updated_at_gte=updated_at_gte,
                      updated_at_lte=updated_at_lte)

    if df.empty:
        return pd.DataFrame(columns=columns)

    if "updated_at" in df.columns:
        df["updated_at"] = df["updated_at"].apply(
            lambda ts: datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
            if isinstance(ts, (int, float)) else ts
        )

    if "additions" in df.columns and "deletions" in df.columns:
        df["delta"] = df.apply(format_delta, axis=1)
    else:
        df["delta"] = ""

    if "project_url" in df.columns and "project_name" in df.columns:
        df["项目名称"] = df.apply(
            lambda row: f'<a href="{row["project_url"]}" target="_blank">{row["project_name"]}</a>'
            if pd.notna(row["project_url"]) and row["project_url"] else row["project_name"],
            axis=1
        )

    if "commit_url" in df.columns and "commit_messages" in df.columns:
        df["提交信息"] = df.apply(
            lambda row: f'<a href="{row["commit_url"]}" target="_blank" title="{row["commit_messages"]}">{row["commit_messages"][:40]}{"..." if len(row["commit_messages"]) > 40 else ""}</a>'
            if pd.notna(row["commit_url"]) and row["commit_url"] else row["commit_messages"],
            axis=1
        )

    data = df[columns] if columns else df
    if not columns:
        required_columns = [
            "id", "project_name", "project_url", "author", "branch", 
            "updated_at", "commit_messages", "commit_url", "score", 
            "additions", "deletions", "status"
        ]
        for col in required_columns:
            if col in df.columns:
                data[col] = df[col]
    return data


# 隐藏默认的Streamlit菜单和页眉
st.markdown("""
    <style>
        #MainMenu {visibility: hidden;}
        header {visibility: hidden;}
        footer {visibility: hidden;}
        div.block-container {padding-top: 0rem;}
    </style>
    """, unsafe_allow_html=True)

# 自定义CSS样式
st.markdown(
    """
    <style>
    .main {
        background-color: #f0f2f6;
        padding-top: 0rem;
    }
    .stButton>button {
        background-color: #4CAF50;
        color: white;
        border-radius: 20px;
        padding: 0.5rem 2rem;
        border: none;
        transition: all 0.3s ease;
    }
    .stButton>button:hover {
        background-color: #45a049;
        box-shadow: 0 2px 5px rgba(0,0,0,0.2);
        color: #ffffff;
    }
    .stTextInput>div>div>input {
        border: 1px solid #ccc;
        border-radius: 4px;
        padding: 0.5rem;
    }
    .stCheckbox>div>div>input {
        accent-color: #4CAF50;
    }
    .stDataFrame {
        border: 1px solid #ddd;
        border-radius: 4px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }
    .stMarkdown {font-size: 18px;}
    .login-title {
        text-align: center;
        color: #2E4053;
        margin: 0.5rem 0;
        font-size: 2.2rem;
        font-weight: bold;
    }
    .login-container {
        background-color: white;
        border-radius: 15px;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        margin-top: 0rem;
    }
    .platform-icon {
        font-size: 3.5rem;
        margin-bottom: 0.5rem;
        text-align: center;
    }
    .dataframe-table {
        width: 100%;
        border-collapse: collapse;
        font-size: 14px;
    }
    .dataframe-table th {
        background-color: #4CAF50;
        color: white;
        padding: 10px;
        text-align: left;
    }
    .dataframe-table td {
        padding: 8px;
        border-bottom: 1px solid #ddd;
    }
    .dataframe-table tr:hover {
        background-color: #f5f5f5;
    }
    .dataframe-table a {
        color: #1e88e5;
        text-decoration: none;
    }
    .dataframe-table a:hover {
        text-decoration: underline;
    }
    .dataframe-table th:nth-child(1) { width: 200px; } /* 项目名称 */
    .dataframe-table th:nth-child(2) { width: 100px; } /* 分支 */
    .dataframe-table th:nth-child(3) { width: auto; } /* 提交信息 - 自动调整 */
    .dataframe-table th:nth-child(4) { width: 80px; } /* 提交人 */
    .dataframe-table th:nth-child(5) { width: 100px; } /* 提交时间 */
    .dataframe-table th:nth-child(6) { width: 80px; white-space: pre-line; } /* 变更 - 80 +/- 换行显示 */
    .dataframe-table th:nth-child(7) { width: 60px; } /* 状态 - 使用 √ 符号 */
    .dataframe-table th:nth-child(8) { width: 60px; } /* 得分 */
    .dataframe-table td:nth-child(6) { white-space: pre-line; } /* 变更列换行显示 */
    .table-container {
        max-height: 70vh !important;
        overflow-y: auto !important;
        overflow-x: auto !important;
        display: block !important;
    }
    .table-container table {
        display: block !important;
    }
    .sortable {
        cursor: pointer;
        user-select: none;
    }
    .sortable:hover {
        background-color: #45a049;
    }
    .sort-asc::after {
        content: " ▲";
    }
    .sort-desc::after {
        content: " ▼";
    }
    </style>
    <script>
    function sortTable(n) {
        var table = document.querySelector(".dataframe-table");
        if (!table) return;
        
        // 获取数据行（排除表头）
        var tbody = table.tBodies[0] || table;
        var dataRows = Array.from(tbody.rows);
        var ascending = table.getAttribute("data-sort-col") != n || table.getAttribute("data-sort-dir") != "asc";

        dataRows.sort(function(row1, row2) {
            var cell1 = row1.cells[n];
            var cell2 = row2.cells[n];
            if (!cell1 || !cell2) return 0;
            var val1 = cell1.textContent || cell1.innerText;
            var val2 = cell2.textContent || cell2.innerText;

            // 处理状态列的特殊情况（√ 和 ×）
            if (n === 6) { // 状态列索引
                var statusOrder = {'√': 1, '×': 2, 'success': 1, 'failed': 2};
                var status1 = statusOrder[val1.trim()] || 999;
                var status2 = statusOrder[val2.trim()] || 999;
                return ascending ? status1 - status2 : status2 - status1;
            }

            // 处理数值列（得分列）
            if (n === 7) { // 得分列索引
                var num1 = parseFloat(val1.replace(/[^0-9.-]/g, ""));
                var num2 = parseFloat(val2.replace(/[^0-9.-]/g, ""));
                if (!isNaN(num1) && !isNaN(num2)) {
                    return ascending ? num1 - num2 : num2 - num1;
                }
            }

            // 处理日期时间列
            if (n === 4) { // 提交时间列索引
                var date1 = new Date(val1);
                var date2 = new Date(val2);
                if (!isNaN(date1.getTime()) && !isNaN(date2.getTime())) {
                    return ascending ? date1 - date2 : date2 - date1;
                }
            }

            // 默认文本排序
            return ascending ? val1.localeCompare(val2) : val2.localeCompare(val1);
        });

        // 清空表格体并重新添加排序后的数据行
        tbody.innerHTML = '';
        dataRows.forEach(function(row) {
            tbody.appendChild(row);
        });

        table.setAttribute("data-sort-col", n);
        table.setAttribute("data-sort-dir", ascending ? "asc" : "desc");

        var headers = table.querySelectorAll("th");
        headers.forEach(function(th, i) {
            th.classList.remove("sort-asc", "sort-desc");
            if (i === n) {
                th.classList.add(ascending ? "sort-asc" : "sort-desc");
            }
        });
    }

    function initSortable() {
        var headers = document.querySelectorAll(".dataframe-table th");
        headers.forEach(function(th, i) {
            th.classList.add("sortable");
            th.onclick = function() { sortTable(i); };
        });
    }

    // 使用 MutationObserver 监听表格动态加载
    var observer = new MutationObserver(function(mutations) {
        mutations.forEach(function(mutation) {
            mutation.addedNodes.forEach(function(node) {
                if (node.querySelector && node.querySelector(".dataframe-table")) {
                    setTimeout(initSortable, 100); // 延迟初始化确保DOM完全加载
                } else if (node.classList && node.classList.contains("dataframe-table")) {
                    setTimeout(initSortable, 100);
                } else if (node.innerHTML && node.innerHTML.includes('dataframe-table')) {
                    setTimeout(initSortable, 100);
                }
            });
        });
    });

    observer.observe(document.body, { childList: true, subtree: true });

    // 页面加载后也尝试初始化一次
    window.addEventListener('load', function() {
        setTimeout(initSortable, 500);
    });

    // 定期检查新表格（备用方案）
    setInterval(initSortable, 2000);
    </script>
    """,
    unsafe_allow_html=True
)


# 登录界面
def login_page():
    # 使用 st.columns 创建居中布局
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown('<div class="login-container">', unsafe_allow_html=True)
        st.markdown('<div class="platform-icon">🤖</div>', unsafe_allow_html=True)
        st.markdown('<h1 class="login-title">AI代码审查平台</h1>', unsafe_allow_html=True)

        # 如果用户名和密码都为 'admin'，提示用户修改密码
        if DASHBOARD_USER == "admin" and DASHBOARD_PASSWORD == "admin":
            st.warning(
                "安全提示：检测到默认用户名和密码为 'admin'，存在安全风险！\n\n"
                "请立即修改：\n"
                "1. 打开 `.env` 文件\n"
                "2. 修改 `DASHBOARD_USER` 和 `DASHBOARD_PASSWORD` 变量\n"
                "3. 保存并重启应用"
            )
            st.write(f"当前用户名: `{DASHBOARD_USER}`, 当前密码: `{DASHBOARD_PASSWORD}`")

        # 获取保存的用户名和密码
        saved_username, saved_password = get_saved_credentials()

        # 创建一个form，支持回车提交
        with st.form("login_form", clear_on_submit=False):
            username = st.text_input("👤 用户名", value=saved_username)
            password = st.text_input("🔑 密码", type="password", value=saved_password)
            remember_password = st.checkbox("记住密码", value=bool(saved_username))
            submit = st.form_submit_button("登 录")

            if submit:
                if authenticate(username, password, remember_password):
                    st.rerun()  # 重新运行应用以显示主要内容
                else:
                    st.error("用户名或密码错误")
        st.markdown('</div>', unsafe_allow_html=True)


# 退出登录函数
def logout():
    # 清除session状态
    st.session_state['login_status'] = False
    st.session_state.pop('username', None)
    st.session_state.pop('saved_username', None)

    # 清除cookie
    if 'auth_token' in cookies:
        del cookies['auth_token']
    cookies.save()

    st.rerun()


# 主要内容
def main_page():
    # 将标题和退出按钮放在同一行
    col_title, col_space, col_logout = st.columns([7, 2, 1.2])
    with col_title:
        st.markdown("#### 📊 代码审查记录")
    with col_logout:
        if st.button("退出登录", key="logout_button", use_container_width=True):
            logout()

    current_date = datetime.date.today()
    start_date_default = current_date - datetime.timedelta(days=7)

    def display_push_data(tab, service_func):
        with tab:
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                start_date = st.date_input("开始日期", start_date_default, key=f"{tab}_start_date")
            with col2:
                end_date = st.date_input("结束日期", current_date, key=f"{tab}_end_date")

            start_datetime = datetime.datetime.combine(start_date, datetime.time.min)
            end_datetime = datetime.datetime.combine(end_date, datetime.time.max)

            data = get_data(service_func, updated_at_gte=int(start_datetime.timestamp()),
                            updated_at_lte=int(end_datetime.timestamp()))
            df = pd.DataFrame(data)

            unique_authors = sorted(df["author"].dropna().unique().tolist()) if not df.empty else []
            unique_projects = sorted(df["project_name"].dropna().unique().tolist()) if not df.empty else []
            with col3:
                authors = st.multiselect("开发者", unique_authors, default=[], key=f"{tab}_authors")
            with col4:
                project_names = st.multiselect("项目名称", unique_projects, default=[], key=f"{tab}_projects")

            data = get_data(service_func, authors=authors, project_names=project_names,
                            updated_at_gte=int(start_datetime.timestamp()),
                            updated_at_lte=int(end_datetime.timestamp()))
            df = pd.DataFrame(data)

            if not df.empty:
                # 预处理数据
                df_display = df.copy()
                
                # 创建 delta 列
                if "additions" in df_display.columns and "deletions" in df_display.columns:
                    df_display["delta"] = df_display.apply(format_delta, axis=1)
                
                # 格式化状态
                if "status" in df_display.columns:
                    df_display["status"] = df_display["status"].apply(format_status)
                
                df_display = df_display.reset_index(drop=True)

                # 检查并修复空的项目名称
                if "project_name" in df_display.columns:
                    # 如果 project_name 为空但 project_url 不为空，尝试从 URL 提取项目名
                    def fix_project_name(row):
                        if pd.isna(row["project_name"]) or str(row["project_name"]).strip() == "":
                            if pd.notna(row["project_url"]) and str(row["project_url"]).strip():
                                # 从 URL 提取项目名（最后一个 / 后的部分）
                                url = str(row["project_url"]).rstrip('/')
                                if '/' in url:
                                    return url.split('/')[-1]
                        return row["project_name"]

                    df_display["project_name"] = df_display.apply(fix_project_name, axis=1)

                    # 确保所有项目名称都有值
                    df_display["project_name"] = df_display["project_name"].fillna("Unknown Project")

                # 处理项目名称和分支的显示逻辑
                has_project_url = "project_url" in df_display.columns and not df_display["project_url"].isna().all()

                if not has_project_url:
                    # 旧数据：没有 project_url，直接显示项目名称和分支名称
                    push_column_config = {
                        "project_name": st.column_config.TextColumn("项目名称", max_chars=100),
                        "branch": st.column_config.TextColumn("分支"),
                        "author": st.column_config.TextColumn("提交人"),
                        "updated_at": st.column_config.TextColumn("提交时间"),
                        "delta": st.column_config.TextColumn("变更"),
                        "status": st.column_config.TextColumn(
                            "状态",
                            help="√=成功, ×=失败"
                        ),
                        "score": st.column_config.NumberColumn(
                            "得分",
                            format="%.1f"
                        ),
                    }
                    # 旧数据显示列 - 不增加额外列
                    display_columns = ["project_name", "branch", "author", "updated_at", "delta", "status", "score"]
                else:
                    # 新数据：有 project_url，创建分支链接
                    if "branch" in df_display.columns:
                        def create_branch_url(row):
                            if pd.notna(row["project_url"]) and pd.notna(row["branch"]):
                                project_url = row["project_url"].rstrip('/')
                                branch = row["branch"]
                                
                                # 根据不同的代码托管平台构建分支URL
                                if "gitlab" in project_url.lower():
                                    return f"{project_url}/-/tree/{branch}"
                                elif "github.com" in project_url.lower():
                                    return f"{project_url}/tree/{branch}"
                                elif "bitbucket.org" in project_url.lower():
                                    return f"{project_url}/src/{branch}"
                                else:
                                    # 默认尝试 GitLab 格式（也适用于其他类 GitLab 平台）
                                    return f"{project_url}/-/tree/{branch}"
                            return ""
                        
                        df_display["branch_url"] = df_display.apply(create_branch_url, axis=1)
                    else:
                        df_display["branch_url"] = ""

                    # commit_url 已经在 get_data 函数中处理，直接使用

                    push_column_config = {
                        "project_name": st.column_config.TextColumn("项目名称", max_chars=100),
                        "project_url": None,  # 隐藏原始URL列
                        "branch": None,  # 隐藏原始分支列
                        "branch_url": st.column_config.LinkColumn(
                            "分支",
                            max_chars=100,
                            validate=r"^https?://.+",
                            display_text=r"https?://.*/(?:tree|src/branch|src)/([^/]+)(?:/.*)?$"  # 从URL提取分支名
                        ) if not df_display["branch_url"].eq("").any() else st.column_config.TextColumn("分支"),
                        "author": st.column_config.TextColumn("提交人"),
                        "updated_at": st.column_config.TextColumn("提交时间"),
                        "delta": st.column_config.TextColumn("变更"),
                        "status": st.column_config.TextColumn(
                            "状态",
                            help="√=成功, ×=失败"
                        ),
                        "score": st.column_config.NumberColumn(
                            "得分",
                            format="%.1f"
                        ),
                    }
                    # 新数据显示列
                    display_columns = ["project_name", "project_url", "branch", "branch_url", "commit_messages", "commit_url", "author", "updated_at", "delta", "status", "score"]
                
                # 使用AgGrid实现高级表格功能
                from st_aggrid import AgGrid, GridOptionsBuilder, JsCode

                # 创建通用单元格渲染器类（支持项目名称、分支、提交信息）
                custom_cell_renderer = JsCode("""
                class LinkCellRenderer {
                    init(params) {
                        this.eGui = document.createElement('div');
                        var column = params.column ? params.column.getColId() : '';
                        var urlField = '';
                        
                        // 根据列名确定使用哪个 URL 字段
                        if (column === 'project_name') {
                            urlField = 'project_url';
                        } else if (column === 'branch') {
                            urlField = 'branch_url';
                        } else if (column === 'commit_messages') {
                            urlField = 'commit_url';
                        }
                        
                        var url = urlField && params.data[urlField] ? params.data[urlField].trim() : '';
                        
                        if (url && url !== '') {
                            // 创建链接
                            var link = document.createElement('a');
                            link.href = url;
                            link.target = '_blank';
                            link.style.color = '#1e88e5';
                            link.style.textDecoration = 'none';
                            // 分支列显示纯文本（不显示URL）
                            if (column === 'branch') {
                                var match = url.match(/.*\/tree\/([^/]+)(?:\/.*)?$/);
                                link.textContent = params.value || (match ? match[1] : url);
                            } else {
                                link.textContent = params.value || url;
                            }
                            this.eGui.appendChild(link);
                        } else {
                            // 创建纯文本
                            this.eGui.textContent = params.value || '';
                        }
                    }

                    getGui() {
                        return this.eGui;
                    }

                    destroy() {
                        // 清理操作
                    }
                }
                """)

                # 配置所有列，确保正确的顺序
                ordered_columns = ["project_name", "project_url", "branch", "branch_url", "commit_messages", "commit_url", "author", "updated_at", "delta", "status", "score"]

                # 过滤出实际存在的列
                available_columns = [col for col in ordered_columns if col in df_display.columns]

                # 重新排序DataFrame以匹配所需的列顺序
                df_display = df_display[available_columns]

                # 配置AgGrid
                gb = GridOptionsBuilder.from_dataframe(df_display)

                # 配置项目名称列 - 支持链接和文本混排
                gb.configure_column(
                    "project_name",
                    headerName="项目名称",
                    cellRenderer=custom_cell_renderer,
                    sortable=True,
                    filter=True,
                    width=150,
                    maxWidth=150,
                    minWidth=150
                )

                # 配置隐藏的 URL 字段，供渲染器使用但不显示
                hidden_url_columns = ["project_url", "branch_url", "commit_url"]
                for col in hidden_url_columns:
                    if col in available_columns:
                        gb.configure_column(
                            col,
                            hide=True
                        )

                # 按顺序配置每列
                for col in available_columns:
                    if col in ["project_name", "project_url", "branch_url", "commit_url"]:
                        # 已配置，跳过
                        continue
                    elif col == "branch":
                        gb.configure_column(
                            col,
                            headerName="分支",
                            cellRenderer=custom_cell_renderer,
                            sortable=True,
                            filter=True,
                            width=120,
                            maxWidth=120,
                            minWidth=120
                        )
                    elif col == "commit_messages":
                        gb.configure_column(
                            col,
                            headerName="提交信息",
                            cellRenderer=custom_cell_renderer,
                            sortable=True,
                            filter=True,
                            minWidth=200,
                            flex=1  # 根据剩余宽度动态调整
                        )
                    elif col == "delta":
                        gb.configure_column(
                            col,
                            headerName="变更",
                            sortable=True,
                            filter=True,
                            width=80,
                            maxWidth=80,
                            minWidth=80
                        )
                    elif col == "author":
                        gb.configure_column(
                            col,
                            headerName="提交人",
                            sortable=True,
                            filter=True,
                            width=80,
                            maxWidth=80,
                            minWidth=80
                        )
                    elif col == "updated_at":
                        gb.configure_column(
                            col,
                            headerName="提交时间",
                            sortable=True,
                            filter=True,
                            width=160,
                            maxWidth=160,
                            minWidth=160
                        )
                    elif col == "status":
                        gb.configure_column(
                            col,
                            headerName="状态",
                            sortable=True,
                            filter=True,
                            width=60,
                            maxWidth=60,
                            minWidth=60
                        )
                    elif col == "score":
                        gb.configure_column(
                            col,
                            headerName="得分",
                            sortable=True,
                            filter=True,
                            width=60,
                            maxWidth=60,
                            minWidth=60
                        )

                # 配置表格选项
                gb.configure_grid_options(
                    domLayout='normal',
                    enableRangeSelection=True,
                    pagination=True,
                    paginationAutoPageSize=True
                )

                grid_options = gb.build()

                # 显示AgGrid表格
                AgGrid(
                    df_display,
                    gridOptions=grid_options,
                    height=500,
                    fit_columns_on_grid_load=False,  # 使用 flex 布局时关闭自动适应
                    allow_unsafe_jscode=True,
                    theme='streamlit'
                )

            if not df.empty:
                total_records = len(df)
                successful_records = len(df[df['status'] == "√"]) if 'status' in df.columns else total_records
                failed_records = len(df[df['status'] == "×"]) if 'status' in df.columns else 0
                average_score = df["score"].mean() if "score" in df.columns else 0
                st.markdown(f"**总记录数:** {total_records} | **成功:** {successful_records} | **失败:** {failed_records} | **平均得分:** {average_score:.2f}")

    # 根据环境变量决定是否显示 push_tab
    show_push_tab = os.environ.get('PUSH_REVIEW_ENABLED', '0') == '1'

    if show_push_tab:
        push_tab, mr_tab = st.tabs(["代码推送", "合并请求"])
    else:
        mr_tab = st.container()

    def display_data(tab, service_func, columns, column_config):
        with tab:
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                start_date = st.date_input("开始日期", start_date_default, key=f"{tab}_start_date")
            with col2:
                end_date = st.date_input("结束日期", current_date, key=f"{tab}_end_date")

            start_datetime = datetime.datetime.combine(start_date, datetime.time.min)
            end_datetime = datetime.datetime.combine(end_date, datetime.time.max)

            data = get_data(service_func, updated_at_gte=int(start_datetime.timestamp()),
                            updated_at_lte=int(end_datetime.timestamp()), columns=columns)
            df = pd.DataFrame(data)

            unique_authors = sorted(df["author"].dropna().unique().tolist()) if not df.empty else []
            unique_projects = sorted(df["project_name"].dropna().unique().tolist()) if not df.empty else []
            with col3:
                authors = st.multiselect("开发者", unique_authors, default=[], key=f"{tab}_authors")
            with col4:
                project_names = st.multiselect("项目名称", unique_projects, default=[], key=f"{tab}_projects")

            data = get_data(service_func, authors=authors, project_names=project_names,
                            updated_at_gte=int(start_datetime.timestamp()),
                            updated_at_lte=int(end_datetime.timestamp()), columns=columns)
            df = pd.DataFrame(data)

            for col in ["project_url", "commit_url"]:
                if col in df.columns:
                    df[col] = df[col].astype(str)

            st.data_editor(
                df,
                use_container_width=True,
                column_config=column_config,
                disabled=True  # 数据只读，不允许编辑
            )

            # 显示统计信息
            if not df.empty:
                total_records = len(df)
                successful_records = len(df[df['status'] == 'success']) if 'status' in df.columns else total_records
                failed_records = len(df[df['status'] == 'failed']) if 'status' in df.columns else 0
                average_score = df["score"].mean() if "score" in df.columns else 0
                st.markdown(f"**总记录数:** {total_records} | **成功:** {successful_records} | **失败:** {failed_records} | **平均得分:** {average_score:.2f}")

    # Merge Request 数据展示
    mr_columns = ["project_name", "project_url", "author", "source_branch", "target_branch", "updated_at", "commit_messages", "commit_url", "delta",
                  "score", "url", 'additions', 'deletions', 'status', 'id']

    mr_column_config = {
        "project_name": None,
        "project_url": st.column_config.LinkColumn(
            "项目名称",
            max_chars=100,
        ),
        "author": "开发者",
        "source_branch": "源分支",
        "target_branch": "目标分支",
        "updated_at": "更新时间",
        "commit_messages": None,
        "commit_url": st.column_config.LinkColumn(
            "提交信息",
            max_chars=100,
        ),
        "score": st.column_config.ProgressColumn(
            "得分",
            format="%f",
            min_value=0,
            max_value=100,
        ),
        "url": st.column_config.LinkColumn(
            "操作",
            max_chars=100,
            display_text="查看 MR"
        ),
        "additions": None,
        "deletions": None,
        "status": st.column_config.TextColumn(
            "状态",
            help="success=成功, failed=失败",
        ),
        "id": None,  # 隐藏 ID 列
    }

    display_data(mr_tab, ReviewService().get_mr_review_logs, mr_columns, mr_column_config)

    # Push 数据展示
    if show_push_tab:
        display_push_data(push_tab, ReviewService().get_push_review_logs)




# 应用入口
if check_login_status():
    main_page()
else:
    login_page()
