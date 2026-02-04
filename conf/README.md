# 多语言代码审查提示词配置说明

本项目支持针对不同编程语言的差异化代码审查提示词，每种语言都有专门的审查要点和最佳实践。

## 📁 提示词文件列表

| 文件 | 对应语言 | 文件扩展名 |
|------|---------|-----------|
| `python_prompt.yml` | Python | `.py` |
| `java_prompt.yml` | Java | `.java` |
| `javascript_prompt.yml` | JavaScript / TypeScript | `.js`, `.ts`, `.jsx`, `.tsx` |
| `golang_prompt.yml` | Go (Golang) | `.go` |
| `cpp_prompt.yml` | C++ | `.cpp`, `.cc`, `.cxx`, `.hpp`, `.h` |
| `php_prompt.yml` | PHP | `.php` |
| `sql_prompt.yml` | SQL | `.sql` |
| `ruby_prompt.yml` | Ruby / Ruby on Rails | `.rb` |
| `prompt_templates.yml` | 通用（默认） | 其他所有类型 |

## 🎯 语言特定审查要点

每种语言的提示词都包含该语言特有的审查维度：

### Python
- PEP 8 规范遵守（命名、缩进、导入排序）
- Python 最佳实践（列表推导式、上下文管理器、类型注解）
- Python 安全性（eval/exec 危险函数、反序列化安全）
- 性能优化（循环优化、GIL 限制下的多线程）
- Python 陷阱（可变默认参数、闭包延迟绑定、深浅拷贝）

### Java
- Java 编码规范（命名、包规范、类长度控制）
- 空指针和异常处理（Optional、try-with-resources）
- 集合与并发（线程安全、并发工具类）
- Java 性能（StringBuilder、Stream API）
- 设计模式（SOLID 原则、接口与抽象类）

### JavaScript / TypeScript
- ES6+ 语法和现代 JS 特性（箭头函数、解构、模块化）
- TypeScript 类型安全（避免 any、接口完整性）
- 异步编程（Promise、async/await、竞态条件）
- DOM 安全和性能（XSS 防护、重绘回流）
- 前端框架最佳实践（React/Vue/Angular）

### Go (Golang)
- Go 编码规范（Effective Go、gofmt）
- 错误处理哲学（显式错误检查、panic 使用场景）
- 并发编程（Goroutine 泄露、Channel、Race Condition）
- 接口和类型设计（小接口、类型断言）
- Go 陷阱（nil 切片、defer 执行时机、闭包循环变量）

### C++
- 内存安全（智能指针、内存泄漏、悬空指针）
- 现代 C++ 特性（RAII、移动语义、Lambda）
- 异常安全（构造函数异常、析构函数不抛异常）
- 多线程和并发（数据竞争、死锁）
- C++ 陷阱（隐式转换、虚析构函数、三/五法则）

### PHP
- 安全性重点（SQL 注入、XSS、CSRF、文件上传）
- PHP 最佳实践（类型声明、Composer、PSR 规范）
- 性能优化（N+1 查询、缓存、字符串拼接）
- 框架规范（Laravel/Symfony/CodeIgniter）
- PHP 陷阱（弱类型比较、变量作用域、时区处理）

### SQL
- 性能优化（索引使用、查询复杂度、N+1 问题）
- SQL 注入防范（参数化查询、禁止字符串拼接）
- 事务和数据一致性（事务范围、死锁、隔离级别）
- 数据库特定优化（MySQL EXPLAIN、PostgreSQL 索引类型）
- 数据安全和隐私（敏感数据脱敏、审计日志）

### Ruby / Ruby on Rails
- Ruby 惯用写法（unless、until、块、Proc、Lambda）
- Rails 最佳实践（MVC 分层、ActiveRecord、验证器）
- 性能优化（N+1 查询、缓存、背景任务）
- 安全性（SQL 注入、XSS、CSRF、credentials）
- Ruby 陷阱（可变默认参数、运算符优先级、冻结字符串）

## 🏗️ 提示词模板架构（优化版）

为了避免重复内容，提示词文件采用了**基础模板 + 语言特定检查**的分层架构。

### 文件结构

```
conf/
├── base_prompt.yml           # 基础模板（评分规则、输出格式、风格说明）
├── python_prompt.yml        # Python 特定审查要点
├── java_prompt.yml          # Java 特定审查要点
├── javascript_prompt.yml    # JS/TS 特定审查要点
├── golang_prompt.yml        # Go 特定审查要点
├── cpp_prompt.yml           # C++ 特定审查要点
├── php_prompt.yml           # PHP 特定审查要点
├── sql_prompt.yml           # SQL 特定审查要点
├── ruby_prompt.yml          # Ruby 特定审查要点
└── prompt_templates.yml    # 默认通用提示词（兼容旧版本）
```

### 架构说明

#### 基础模板 (`base_prompt.yml`)

包含所有语言通用的部分：
- **评分规则**（5个维度，共100分）
- **输出格式**（Markdown 格式要求）
- **风格模板**（professional/sarcastic/gentle/humorous）
- **用户提示词模板**（可被子类覆盖）

#### 语言特定文件 (`{language}_prompt.yml`)

只包含差异化内容：
- **语言特定检查要点**（该语言特有的审查项）
- **可选的 user_prompt**（覆盖基础模板）

### 模板合并逻辑

```
最终 system_prompt = 
    语言特定检查要点 (来自 xxx_prompt.yml)
    + 评分规则 (来自 base_prompt.yml)
    + 输出格式 (来自 base_prompt.yml)
    + 风格模板 (来自 base_prompt.yml)

最终 user_prompt = 
    xxx_prompt.yml 中的 user_prompt（如果定义了）
    否则使用 base_prompt.yml 中的 user_prompt_template
```

### ✅ 自动语言识别

系统已自动实现语言检测逻辑，**无需手动配置**！

#### 工作原理

1. **文件扩展名识别**：系统自动分析 `changes` 列表中的文件路径
2. **语言统计**：统计各语言文件数量
3. **智能选择**：
   - 某种语言占比 ≥ 50% → 使用该语言的特定提示词
   - 混合语言（没有主导语言）→ 使用默认通用提示词
4. **模板合并**：加载基础模板 + 语言特定检查要点

#### 使用示例

```python
from biz.utils.code_reviewer import CodeReviewer

changes = [
    {'new_path': 'src/main.py', 'diff': '...'},
    {'new_path': 'src/utils.py', 'diff': '...'},
]

reviewer = CodeReviewer(changes=changes)
result = reviewer.review_and_strip_code(str(changes), commits_text, changes=changes)
# 自动使用 Python 特定审查规则
```

#### 日志输出

```
INFO - 检测到主要编程语言: python_prompt (3/3 文件)
INFO - 使用 python_prompt.yml 中的语言特定提示词进行审查
```

### 方案二：环境变量配置

在 `.env` 文件中设置默认语言提示词：

```bash
# 设置默认代码审查语言提示词
DEFAULT_CODE_REVIEW_LANGUAGE=python
```

### 方案三：混合审查

在现有的通用提示词中，添加语言检测逻辑，让 AI 自动识别代码语言并针对性审查。

## ➕ 添加新的语言提示词

要为新的编程语言添加特定审查规则，只需 2 步：

### 步骤 1：创建语言提示词文件

在 `conf/` 目录下创建新的 YAML 文件，例如 `rust_prompt.yml`：

```yaml
code_review_prompt:
  # 只需定义语言特定审查要点
  language_specific_checks: |-
    你是资深 Rust 架构师和代码审查专家...
    
    ### Rust 代码审查要点：
    1. **所有权和借用**：
       - 所有权转移和借用规则遵守
       - 生命周期标注的正确性
       - 避免悬垂引用
    
    2. **内存安全**：
       - unsafe 代码块的合理性
       - 智能指针使用（Box、Rc、Arc）
       - 避免内存泄漏
    
    3. **错误处理**：
       - Result 和 Option 的正确处理
       - 错误传播（? 运算符）
       - panic 使用场景
    
    4. **并发编程**：
       - Send 和 Sync trait 实现
       - 线程安全的数据共享
       - 死锁避免
    
    5. **性能优化**：
       - 零成本抽象使用
       - 迭代器优化
       - 避免不必要的克隆
    
    6. **风格 Emoji**：
       - 🦀 Rust 特色

  # 可选：覆盖基础模板中的 user_prompt
  # user_prompt: |-
  #   自定义的用户提示词...
```

### 步骤 2：注册文件扩展名

编辑 `biz/utils/code_reviewer.py`，在 `EXTENSION_TO_PROMPT` 映射中添加新语言：

```python
EXTENSION_TO_PROMPT = {
    # 已有语言...
    '.py': 'python_prompt',
    '.java': 'java_prompt',
    # ...
    
    # 添加新语言
    '.rs': 'rust_prompt',  # Rust
    '.kt': 'kotlin_prompt',  # Kotlin
    '.swift': 'swift_prompt',  # Swift
}
```

### 完成！

系统会自动识别 `.rs` 文件并使用 `rust_prompt.yml` 中的审查规则。

## 📝 提示词模板变量

所有提示词文件都使用 Jinja2 模板引擎，支持以下变量：

- `{{ style }}` - 审查风格（professional/sarcastic/gentle/humorous）
- `{diffs_text}` - 代码变更内容（diff 格式）
- `{commits_text}` - 提交历史信息

## 🎨 风格说明

每种语言的提示词都支持四种审查风格：

1. **professional（专业型）**：使用标准工程术语，保持专业严谨
2. **sarcastic（讽刺型）**：大胆使用讽刺性语言，技术指正准确
3. **gentle（绅士型）**：多用"建议"、"可以考虑"等温和措辞
4. **humorous（幽默型）**：技术点评中加入幽默元素，使用 Emoji

## 🔧 自定义提示词

如需为特定项目定制提示词，可以：

1. 复制现有语言提示词文件（如 `python_prompt.yml`）
2. 重命名为项目特定名称（如 `python_project_a.yml`）
3. 修改 `system_prompt` 和 `user_prompt` 内容
4. 在代码中根据项目名选择对应的提示词文件

## ⚠️ 注意事项

1. 提示词文件使用 **UTF-8 编码**，请确保编辑器编码设置正确
2. YAML 格式对缩进敏感，请使用空格而非 Tab
3. 多行文本使用 `|-` 符号保持格式
4. Jinja2 模板语法 `{% if %}` 等需要正确闭合

## 📚 参考资源

- **Python**: [PEP 8](https://pep8.org/), [Google Python Style Guide](https://google.github.io/styleguide/pyguide.html)
- **Java**: [Google Java Style Guide](https://google.github.io/styleguide/javaguide.html), [Effective Java](https://www.oreilly.com/library/view/effective-java-3rd/9780134686097/)
- **JavaScript**: [Airbnb JavaScript Style Guide](https://github.com/airbnb/javascript)
- **Go**: [Effective Go](https://go.dev/doc/effective_go), [Go Code Review Comments](https://github.com/golang/go/wiki/CodeReviewComments)
- **C++**: [Google C++ Style Guide](https://google.github.io/styleguide/cppguide.html), [C++ Core Guidelines](https://isocpp.github.io/CppCoreGuidelines/CppCoreGuidelines)
- **PHP**: [PHP The Right Way](https://phptherightway.com/), [PSR Standards](https://www.php-fig.org/psr/)
- **Ruby**: [Ruby Style Guide](https://rubystyle.guide/), [Rails Style Guide](https://rails.rubystyle.guide/)
