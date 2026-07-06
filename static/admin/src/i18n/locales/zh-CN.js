// zh-CN — ground truth bundle for the admin SPA.
//
// Every hard-coded Chinese string currently in static/admin/src/**.vue (and
// the user-facing strings in router/index.js) lives here. T3 will replace
// the in-template literals with t('namespace.key') calls; T5 will translate
// these values into en/ja/ko/es/fr.
//
// Namespace layout follows tech_design §3.5:
//   common         — generic verbs / states reused across pages
//   app            — top-level shell (brand, nav, header tags)
//   dashboard      — DashboardView
//   history        — HistoryView (filters, columns, drawer, enums, toast msgs)
//   demos          — DemosView
//   web            — WebDefaultsView wrapper
//   phone          — PhoneDefaultsView wrapper
//   defaultsForm   — DefaultsForm (shared by web + phone)
//   historySummary — _HistorySummary (Summary block extras toggle)

export default {
  common: {
    unknown: "(unknown)",
    dash: "—",
    online: '在线',
    offline: '离线',
    refresh: '刷新',
    save: '保存',
    cancel: '取消',
    confirm: '确认',
    delete: '删除',
    edit: '编辑',
    create: '新建',
    reset: '恢复',
    loading: '加载中...',
    empty: '暂无数据',
    actions: '操作',
    toggleDark: '切换深色',
    toggleLight: '切换浅色',
    language: '语言',
    yes: '是',
    no: '否',
    all: '全部',
    placeholderDash: '—',
  },

  app: {
    brand: 'Voice Bot Admin',
    sub: '运行时配置 · 场景配置',
    nav: {
      groupOverview: '概览',
      groupConfig: '配置',
      groupCall: '通话',
      groupAdmin: '管理',
      dashboard: 'Dashboard',
      history: '历史记录',
      web: 'Web 默认',
      phone: 'Phone 默认',
      demos: '场景配置',
      mcp: 'MCP 服务器',
      voices: '语音管理',
      activity: '操作日志',
      talk: '通话',
      monitor: '监听',
      myHistory: '我的历史',
      users: '用户管理',
    },
    user: {
      logout: '退出登录',
    },
  },

  login: {
    subtitle: '请登录以继续',
    username: '用户名',
    usernamePlaceholder: '请输入用户名',
    password: '密码',
    passwordPlaceholder: '请输入密码',
    submit: '登录',
    errors: {
      usernameRequired: '请输入用户名',
      passwordRequired: '请输入密码',
      invalidCredentials: '用户名或密码错误',
      generic: '登录失败：{msg}',
    },
  },

  setup: {
    subtitle: '首次访问 · 设置管理员',
    intro: '该部署尚未初始化。请创建第一个管理员账号以继续；创建后将自动登录。',
    username: '用户名',
    usernamePlaceholder: '请设置管理员用户名',
    password: '密码',
    passwordPlaceholder: '请设置管理员密码',
    confirm: '确认密码',
    confirmPlaceholder: '请再次输入密码',
    submit: '创建管理员',
    errors: {
      usernameRequired: '请输入用户名',
      passwordRequired: '请输入密码',
      passwordsMismatch: '两次输入的密码不一致',
      alreadyInitialized: '该部署已初始化，请前往登录页。',
      invalidInput: '用户名和密码不能为空。',
      generic: '创建失败：{msg}',
    },
  },

  dashboard: {
    title: 'Dashboard',
    subtitle: '实时通话指标 · 7s 轮询',
    updatedAt: '· 更新于 {time}',
    statusOnline: '指标在线',
    statusFailed: '指标拉取失败',
    refresh: '刷新',
    notice: {
      header: '口径说明',
      body:
        '<strong>Active calls</strong> 来自进程内 ACTIVE_SESSIONS（phone + web 都计入）；' +
        '<strong>Today / 24h 系列指标</strong>（总数、平均时长、Outcome / Engine / Demo 分布、转人工率、峰值并发）' +
        '基于 DDB 表 <code>genaiic-voicebot-call-history</code>，<strong>仅 phone 通话落表</strong>，web 会话不持久化。',
    },
    cards: {
      activeCalls: 'Active calls (phone + web)',
      activeCallsSuffix: 'in-process',
      todayCalls: 'Today phone calls',
      todayCallsSuffix: 'UTC day',
      avgDuration: 'Avg duration today (phone)',
      avgDurationSuffix: 's',
      transferRate: 'Transfer rate 24h (phone)',
      transferRateSuffix: '%',
      topDemo: 'Top demo 24h (phone)',
      peakConcurrent: 'Peak concurrent 24h (phone)',
      peakConcurrentSuffix: 'sweep-line',
    },
    sections: {
      metricsTitle: '核心指标',
      distributionsTitle: '分布',
      outcomeTitle: 'Outcome 24h (phone)',
      engineTitle: 'Engine 24h (phone)',
      demoTitle: 'Demo 24h (phone)',
      total: '共 {n}',
      totalLabel: '总计',
      empty: '暂无数据',
    },
    emptyState: '指标加载失败,请稍后再试或点右上角刷新。',
    messages: {
      loadFailed: 'Dashboard 指标加载失败: {msg}',
    },
  },

  history: {
    title: '历史记录',
    subtitle: '通话历史浏览 · DDB 游标分页 · 支持筛选 / CSV / Markdown 导出 / 按需摘要',
    filters: {
      caller: 'Caller',
      callerPlaceholder: '+15550001111',
      outcome: 'Outcome',
      engine: 'Engine',
      demo: 'Demo',
      dateRange: '日期范围 (UTC)',
      all: '全部',
    },
    columns: {
      startedAt: 'Started (UTC)',
      caller: 'Caller',
      outcome: 'Outcome',
      engine: 'Engine',
      demo: 'Demo',
      duration: 'Duration',
      summary: 'Summary',
      actions: '操作',
    },
    emptyTitle: '未找到通话',
    emptyDesc: '当前筛选条件下没有匹配的通话记录。请调整上方筛选或等待新通话写入。',
    actions: {
      refresh: '刷新',
      view: 'View',
      exportCsv: '导出 CSV',
      downloadMd: '下载 MD',
      summarize: '生成摘要',
      loadMore: '加载更多',
      noMore: '没有更多了',
      loadedRows: '已加载 {n} 行',
    },
    detail: {
      titlePrefix: 'Call {id}',
      caller: 'Caller',
      startedAt: 'Started (UTC)',
      endedAt: 'Ended (UTC)',
      duration: 'Duration',
      engine: 'Engine',
      demo: 'Demo',
      lang: 'Lang',
      outcome: 'Outcome',
      transferred: 'Transferred',
      transferYes: '是',
      transferNo: '否',
      turns: 'Turns',
      summary: 'Summary',
      transcript: 'Transcript',
      noTurns: '没有 turns 数据',
      noSummary: '[未生成]',
    },
    enums: {
      outcome: {
        user_requested: '用户挂断',
        task_completed: '任务完成',
        transferred: '已转人工',
        timeout: '超时',
        error: '错误',
        unknown: '未知',
      },
      summary: {
        ok: '已生成',
        pending: '待生成',
        failed: '生成失败',
      },
    },
    messages: {
      loadFailed: '加载失败: {msg}',
      loadMoreFailed: '加载更多失败: {msg}',
      detailFailed: '加载详情失败: {msg}',
      summaryUpdated: '摘要已更新',
      summarizeFailed: '生成摘要失败: {msg}',
    },
  },

  demos: {
    title: '场景配置',
    subtitle: 'data/<demo>/manifest.yaml + kb.md + 全局工具库 自动发现',
    actions: {
      rescan: '重新扫描',
      reset: '恢复',
      save: '保存',
      startTalk: '起对话',
    },
    notice:
      '添加新 demo: <code>mkdir data/&lt;demo-id&gt;/</code> 放入 ' +
      '<code>manifest.yaml</code> + <code>kb.md</code>，点"重新扫描"即可生效。' +
      'Tools 由全局工具库 (<code>tools/registry.py</code>) 提供。' +
      '在右侧编辑该配置的各项；保存即写库，下一通生效。',
    columns: {
      id: 'ID',
      label: 'Label',
      lang: 'Main Language',
      kbChars: 'KB 字符',
      tools: 'Tools',
      actions: '操作',
    },
    emptyTitle: '未发现 Demo',
    emptyDesc: '在 data/ 下新建一个含 manifest.yaml + kb.md 的 demo 目录，然后点击重新扫描即可收录。',
    listBadges: {
      tools: '{n} 个工具',
    },
    detail: {
      emptyTitle: '请选择一个场景',
      emptyDesc: '从左侧列表中选择一个场景，即可查看并编辑其配置。',
      id: 'ID',
      mainLang: '主语言',
      kbChars: 'KB 字符数',
      tags: '标签',
      tabs: {
        info: '基本信息',
        system: 'System Prompt',
        greeting: 'Greeting',
        kbIntro: 'KB 开场',
        kbAck: 'KB 应答',
        kb: 'KB 正文',
        tools: 'Tools',
        mcp: 'MCP 服务器',
        translate: '一键翻译',
        filler: '语气词 filler',
      },
      groups: {
        info: '基本信息',
        prompts: '提示词',
        kb: '知识库',
        tools: '工具',
      },
      info: {
        hint: '编辑显示名称、默认语言和标签。保存后在下一次新会话生效。',
        label: '名称',
        labelPlaceholder: '显示名称',
        lang: '默认语言',
        langPlaceholder: '选择默认语言',
        tags: '标签',
      },
      langField: {
        hint: '按语言编辑文本。保存会用当前列出的全部语言整体替换该字段。',
        addLang: '添加语言',
        empty: '暂无内容 — 添加一种语言开始编辑。',
      },
      kbEditWarning:
        '这里只显示每种语言的前 500 个字符。保存会用所显示的内容整体替换知识库正文全文 —— 除非你确实要覆盖整份 KB，否则不要保存。',
      kbHint: '前 500 字符 · 完整内容请直接看 kb.md',
      toolsHint:
        '勾选要为该 demo 启用的 LLM 工具。保存后写回 ' +
        '<code>data/{id}/manifest.yaml</code> 的 ' +
        '<code>tools:</code> 字段，并立即生效（下一通新会话）。',
      noTools: {
        header: '未发现可用工具',
        body:
          '<code>GET /api/admin/tools</code> 返回空列表 — 请检查后端 ' +
          '<code>tools/registry.py</code> 是否已就绪。',
      },
      mcpHint:
        '勾选要为该 demo 挂载的 MCP 服务器。保存后写回 ' +
        '<code>data/{id}/manifest.yaml</code> 的 ' +
        '<code>mcp_servers:</code> 字段，并在下一通新会话生效。',
      mcpDisabledTag: '已禁用',
      mcpMissingTag: '不存在',
      noMcp: {
        header: '没有可用的 MCP 服务器',
        body:
          '尚未注册任何 MCP 服务器 — 请先在 <strong>MCP 服务器</strong> ' +
          '页面添加，再回到这里挂载。',
      },
      fillerHint:
        '配置该 demo 的超时语气词 filler（如「让我查一下」）。保存后写回 ' +
        '<code>data/{id}/manifest.yaml</code> 的 ' +
        '<code>filler:</code> 字段，并在下一通新会话生效。',
      filler: {
        enabled: '启用',
        timeout: '超时',
        probability: '概率',
        phrases: '自定义语气词',
        phrasesHint: '留空则使用该通话语言的全局语气词池。',
        unconfiguredHint: '未配置时用全局默认。',
      },
      asrFilter: {
        title: 'ASR 过滤器',
        hint: '为该 demo 丢弃低置信度的短 ASR 转写（幻听）。保存后写回 manifest 的 asr_filter: 字段，下次新会话生效。',
        enabled: '启用',
        minConfidence: '最低置信度',
        maxChars: '最多 CJK 字符数',
        maxWords: '最多拉丁词数',
        unconfiguredHint: '留空 = 继承全局 / 默认的 ASR 过滤器配置。',
      },
      engineVoice: {
        title: '引擎与音色',
        engine: '引擎',
        provider: 'TTS 供应商',
        voice: '音色',
        model: 'LLM(模型)',
        inheritOption: '继承（跟随会话/全局）',
        inheritHint: '留空 = 跟随会话/全局默认。这里设置的引擎/音色在启动该场景时优先生效（场景 > 会话 > 全局）。',
      },
    },
    messages: {
      loadFailed: '加载 Demo 列表失败: {msg}',
      toolsLoadFailed: '加载工具库失败: {msg}',
      rescanDone: '扫描完成，发现 {n} 个 demo',
      rescanFailed: '扫描失败: {msg}',
      toolsSaved: 'Tools 已保存',
      mcpSaved: 'MCP 服务器已保存',
      fillerSaved: 'filler 配置已保存',
      asrFilterSaved: 'ASR 过滤器配置已保存',
      engineVoiceSaved: '引擎与音色已保存',
      infoSaved: 'Demo 信息已保存',
      langFieldSaved: '已保存',
      mcpLoadFailed: '加载 MCP 服务器失败: {msg}',
      saveFailed: '保存失败: {msg}',
      detailFailed: '加载详情失败: {msg}',
    },
    translate: {
      hint:
        '选择目标语言一键翻译该 demo 的本地化字段（system / greeting 等），' +
        '由 LLM 生成后可在下方校对，再确认写回 ' +
        '<code>data/{id}/manifest.yaml</code>。',
      selectPlaceholder: '选择目标语言',
      translateBtn: '翻译',
      optionPresent: '已存在',
      optionMissing: '缺失',
      missingHint: '该 demo 缺 {lang}，点击翻译一键生成。',
      existsHint: '{lang} 已存在，写回需确认覆盖。',
      previewTitle: '译文预览（{lang}）',
      previewHint: '请校对以下译文，确认无误后点击写回。',
      sourceLabel: '源语言：{lang}',
      writeBackBtn: '确认写回',
      messages: {
        empty: '该 demo 没有可翻译的本地化字段',
        translateFailed: '翻译失败: {msg}',
        badRequest: '无法翻译: {msg}',
        overwriteNeeded: '{lang} 已存在，请再次点击以确认覆盖写回。',
        writeBackDone: '已写回 {lang}',
        writeBackFailed: '写回失败: {msg}',
      },
    },
  },

  web: {
    title: 'Web 默认配置',
    subtitle: '浏览器 /ws 入口的默认引擎、语言、Demo、音色',
    alert: '保存后，新建浏览器会话生效（刷新页面即拿新默认）。已打开的会话不受影响。',
    routeTitle: 'Web 默认',
  },

  phone: {
    title: 'Phone 默认配置',
    subtitle: 'PSTN 呼入 /phone/ws 默认引擎、语言、Demo、音色',
    alert: '保存后，下一通新通话生效（per-call hot-reload）。进行中的通话不变；不需要重启服务。',
    routeTitle: 'Phone 默认',
  },

  phoneNumbers: {
    title: '电话号码(Chime Voice Connector)',
    subtitle: '实时来自 Chime —— 哪个号码接到哪个 Voice Connector。',
    colVc: 'Voice Connector',
    colVcId: 'VC ID',
    colE164: '电话号码',
    colStatus: '状态',
    none: '无号码',
    empty: '未发现 Chime Voice Connector。',
    error: '无法读取 Chime(缺少权限或未配置):{msg}',
  },

  defaultsForm: {
    sections: {
      engineDemo: '对话引擎与 Demo',
      voice: '音色',
      pipeline: 'Pipeline 模式 (LLM / TTS)',
    },
    pipelineHint: '以下 LLM / TTS / MiniMax 字段仅在 engine = pipeline 时使用; nova-sonic 走端到端不读取它们(音色仍可在上方选择)。',
    polyglot: '全语言',
    fields: {
      engine: 'Engine',
      lang: 'Language',
      demo: 'Demo',
      llmModel: 'LLM Model',
      ttsProvider: 'TTS Provider',
      voiceId: 'Voice ID',
      novaVoiceId: 'Nova Sonic 音色',
      minimaxModel: 'MiniMax Model',
    },
    actions: {
      reset: '恢复',
      save: '保存',
    },
    messages: {
      loadFailed: '加载失败: {msg}',
      noChanges: '没有改动',
      saved: '已保存',
      saveFailed: '保存失败: {msg}',
      restored: '已恢复',
    },
  },

  config: {
    asrFilter: {
      title: 'ASR 过滤器 / ASR hallucination filter',
      enabled: '启用',
      minConfidence: '最小置信度',
      maxChars: '最大中日韩字符数',
      maxWords: '最大拉丁词数',
      note: '默认关闭。仅适用于三段式 pipeline（Nova Sonic 使用服务端 STT）。每个 Demo 的设置会覆盖此项。',
    },
  },

  mcp: {
    title: 'MCP 服务器',
    subtitle: '全局 Model Context Protocol 服务器注册表 · 在 Demo 页面按需挂载',
    notice:
      '这些服务器保存在全局注册表中，可按 demo 挂载。仅允许 ' +
      '<code>sse</code> 与 <code>streamable_http</code> 两种 transport' +
      '（出于安全考虑禁用 <code>stdio</code>）。Header 值为只写 — ' +
      '已存密钥会被掩码，不会回传到浏览器。',
    columns: {
      id: 'ID',
      label: 'Label',
      transport: 'Transport',
      auth: '鉴权',
      url: 'URL',
      enabled: '启用',
    },
    authType: {
      none: '无',
      header: 'Header',
      sigv4: 'AWS SigV4',
    },
    emptyTitle: '暂无 MCP 服务器',
    emptyDesc: '注册一个 Model Context Protocol 服务器后，可在 Demos 页面按需挂载到各 demo。',
    actions: {
      add: '添加服务器',
      test: '测试',
    },
    enabledTag: {
      on: '已启用',
      off: '已禁用',
    },
    form: {
      titleNew: '添加 MCP 服务器',
      titleEdit: '编辑 MCP 服务器',
      id: 'ID',
      idHint: '小写字母、数字与连字符；2–63 字符。创建后不可修改。',
      label: 'Label',
      transport: 'Transport',
      url: 'URL',
      urlPlaceholder: 'https://example.com/mcp',
      enabled: '启用',
      auth: '鉴权',
      sigv4Hint: '连接时使用实例 IAM 角色以 AWS SigV4 签名请求，不保存任何密钥。',
      sigv4Service: 'Service',
      sigv4Region: 'Region',
      headers: 'Headers',
      headersHint: '可选 HTTP header（如 Authorization）。值作为密钥保存，读取时掩码。',
      headerKey: 'Header 名称',
      headerValuePlaceholder: '*** (保持不变)',
      headerValueNewPlaceholder: '值',
      addHeader: '添加 Header',
    },
    deleteConfirm: {
      title: '删除 MCP 服务器',
      body: '删除 MCP 服务器 "{id}"？此操作不可撤销。',
    },
    test: {
      okTitle: '已连接 "{id}" · {n} 个工具',
      okEmpty: '已连接 "{id}"，但未暴露任何工具',
      failTitle: '连接 "{id}" 失败',
    },
    messages: {
      loadFailed: '加载 MCP 服务器失败: {msg}',
      saved: '已保存',
      saveFailed: '保存失败: {msg}',
      deleted: '已删除',
      deleteFailed: '删除失败: {msg}',
      deleteRefused: '无法删除 "{id}" — 仍被以下 demo 挂载: {demos}。请先在那里卸载。',
      testFailed: '测试失败: {msg}',
    },
  },

  voices: {
    title: '语音管理',
    subtitle: '全局可编辑语音库 · MiniMax / Polly / Nova Sonic · 供通话与场景选择器使用',
    notice:
      '语音以 <code>(提供商, 语音 ID)</code> 为键存储于全局语音库。' +
      '在此添加语音后，无需重新部署即可在通话以及场景 / 默认值选择器中选用。' +
      '当语音库表缺失时，机器人会回退到内置的语音常量。',
    providers: {
      minimax: 'MiniMax',
      polly: 'Amazon Polly',
      novaSonic: 'Nova Sonic',
    },
    columns: {
      voiceId: '语音 ID',
      label: '名称',
      gender: '性别',
      language: '语言 / 区域',
      boost: 'Boost',
      engine: '引擎',
      polyglot: '多语种',
    },
    fields: {
      voice_id: '语音 ID',
      label: '名称',
      gender: '性别',
      language: '语言',
      locale: '区域',
      lang_label: '语言标签',
      boost: 'Boost',
      engine: '引擎',
      polyglot: '多语种',
    },
    gender: {
      male: '男',
      female: '女',
      neutral: '中性',
    },
    emptyTitle: '暂无语音',
    emptyDesc: '为该提供商添加语音，使其可在通话与场景选择器中选用。',
    actions: {
      add: '添加语音',
    },
    form: {
      titleNew: '添加语音',
      titleEdit: '编辑语音',
      voiceIdPlaceholder: '例如 moss_audio_xxxx / Joanna / matthew',
    },
    deleteConfirm: {
      title: '删除语音',
      body: '确定删除语音“{id}”？正在使用它的通话将回退到提供商默认语音。此操作不可撤销。',
    },
    messages: {
      loadFailed: '加载语音失败：{msg}',
      saved: '已保存',
      saveFailed: '保存失败：{msg}',
      deleted: '已删除',
      deleteFailed: '删除失败：{msg}',
    },
  },

  activity: {
    title: '操作日志',
    subtitle: '管理操作审计 · 最新优先 · 按操作者 / 类型 / 日期筛选 · 已脱敏的详情',
    filters: {
      actor: '操作者',
      actorPlaceholder: '用户名',
      type: '类型',
      dateRange: '日期范围 (UTC)',
      all: '全部',
    },
    columns: {
      time: '时间 (UTC)',
      actor: '操作者',
      type: '类型',
      target: '对象',
      status: '状态',
      actions: '操作',
    },
    emptyTitle: '暂无操作记录',
    emptyDesc: '没有符合当前筛选条件的审计记录。请调整筛选条件或等待新的管理操作。',
    actions: {
      refresh: '刷新',
      view: '查看',
      loadMore: '加载更多',
      noMore: '没有更多结果',
      loadedRows: '已加载 {n} 行',
    },
    detail: {
      titlePrefix: '{type}',
      time: '时间 (UTC)',
      actor: '操作者',
      type: '类型',
      target: '对象',
      status: '状态',
      error: '错误',
      detailMap: '详情',
      noDetail: '未记录详情',
    },
    types: {
      login: '登录',
      logout: '登出',
      'demo-edit': '编辑场景',
      'mcp-upsert': '保存 MCP 服务器',
      'mcp-delete': '删除 MCP 服务器',
      'config-web': '更新 Web 默认值',
      'config-phone': '更新电话默认值',
      'user-create': '创建用户',
      'user-update': '更新用户',
      'user-delete': '删除用户',
      'voice-create': '创建语音',
      'voice-update': '更新语音',
      'voice-delete': '删除语音',
      'call-start': '通话开始',
      'call-end': '通话结束',
    },
    messages: {
      loadFailed: '加载失败：{msg}',
      loadMoreFailed: '加载更多失败：{msg}',
    },
  },

  historySummary: {
    moreFields: 'more fields ({n})',
  },

  users: {
    title: '用户管理',
    subtitle: 'JWT 会话账号 · 角色 + 重置密码 + 启用/禁用',
    emptyTitle: '暂无用户',
    emptyDesc: '创建第一个用户账号以授予控制台访问权限。',
    actions: {
      add: '新建用户',
      makeAdmin: '设为管理员',
      makeUser: '设为普通用户',
      resetPw: '重置密码',
      enable: '启用',
      disable: '禁用',
    },
    columns: {
      username: '用户名',
      role: '角色',
      status: '状态',
      createdAt: '创建时间',
    },
    roles: {
      admin: '管理员',
      user: '普通用户',
    },
    status: {
      active: '正常',
      disabled: '已禁用',
    },
    form: {
      titleNew: '创建用户',
      titleResetPw: '重置密码 · {username}',
      username: '用户名',
      usernameHint: '字母、数字、点、连字符和下划线；2 到 64 个字符。',
      password: '密码',
      newPassword: '新密码',
      passwordPlaceholder: '请输入密码',
      role: '角色',
    },
    deleteConfirm: {
      title: '删除用户',
      body: '确定删除用户 “{username}” 吗？此操作不可撤销。',
    },
    messages: {
      loadFailed: '加载用户失败：{msg}',
      created: '已创建用户 “{username}”',
      createFailed: '创建失败：{msg}',
      roleChanged: '“{username}” 的角色已改为 {role}',
      pwReset: '已重置 “{username}” 的密码',
      enabled: '已启用用户 “{username}”',
      disabled: '已禁用用户 “{username}”',
      updateFailed: '更新失败：{msg}',
      deleted: '已删除用户 “{username}”',
      deleteFailed: '删除失败：{msg}',
    },
    guestLink: {
      button: '生成体验链接',
      title: '生成临时体验链接',
      ttl: '有效期',
      ttlOption: '{min} 分钟',
      scenario: '场景（可选）',
      engine: '引擎',
      lang: '语言',
      provider: 'TTS 提供方',
      voice: '音色',
      copy: '复制',
      copied: '已复制链接',
      copyFailed: '复制失败，请手动复制',
      expiry: '到期时间：{time}',
      failed: '生成失败：{msg}',
    },
  },

  // 临时体验链接落地页（tech_design §3.1）。
  guest: {
    validating: '正在校验体验链接…',
    redirecting: '正在进入通话演示…',
    failed: '链接已失效或过期，请向管理员索取新链接',
  },

  // --- Call views merged from the demo SPA (tech_design §3) ---
  // talk / monitor / debug come from the demo views verbatim; myHistory is
  // the demo's per-user call-history view (renamed from `history` to avoid
  // colliding with admin's full HistoryView `history` namespace).
  talk: {
    actions: {
      summarize: '生成对话总结 (Markdown)',
      debug: '调试 / 事件流',
    },
    status: {
      ready: '准备就绪',
      connecting: '连接中…',
      recording: '录音中…',
    },
    button: {
      start: '开始',
      connecting: '连接中…',
      stop: '停止',
    },
    selectors: {
      engine: '引擎',
      language: '语言',
      provider: '语音供应商',
      voice: '音色',
      model: 'LLM',
    },
    defaultsHint: '引擎 / 语言 / 场景由 Admin 配置, 改默认请去 {adminLink}',
    defaultsHintAdminLabel: 'Admin',
    ptt: {
      toggle: '按住说话模式',
      holdToTalk: '按住说话',
      holding: '聆听中…',
      spaceHint: '或长按空格键说话',
    },
    bubbles: {
      empty: '点击中间按钮开始对话',
      whoUser: '我',
      whoBot: 'Bot',
      partial: '实时',
    },
    drawerTitle: '事件流 (调试)',
    drawerClose: '关闭',
    summary: {
      title: '对话总结',
      generating: '生成中…',
      failed: '总结失败: {msg}',
    },
    errors: {
      loadConfig: '加载配置失败: {msg}',
      mic: '麦克风初始化失败: {msg}',
      ws: 'WebSocket 连接失败',
      start: '启动失败: {msg}',
    },
  },
  monitor: {
    status: {
      online: '在线',
      ended: '已结束',
      noCalls: '无通话',
      idle: '空闲',
    },
    refreshTooltip: '立即刷新通话列表',
    empty: {
      noActive: '当前无活跃通话',
      noActiveHint: '拨打 PSTN 号码或在 /talk 页面发起 Web 会话即可在此监听。',
      noSelection: '请选择一通通话',
      noSelectionHint: '在左侧选择一通进行中的通话即可实时查看其事件流。',
      noEvents: '等待事件…',
    },
    callItem: {
      live: 'LIVE',
    },
    rel: {
      seconds: '{n}s ago',
      minutes: '{n}m ago',
      hours: '{n}h ago',
    },
    eventBody: {
      start: '▶ start',
      end: '■ end',
    },
    errors: {
      refresh: '刷新失败: {msg}',
      ws: '监听 WebSocket 错误',
      callEnded: '通话 {id}… 已结束',
    },
  },
  myHistory: {
    filter: {
      refreshTooltip: '立即刷新历史列表',
      counter: '共 {filtered} / {total} 条',
    },
    window: {
      all: '全部',
      today: '今日',
      last7d: '近 7 天',
      last30d: '近 30 天',
    },
    list: {
      empty: '暂无通话历史',
      emptyTitle: '暂无通话',
      loadMore: '加载更多',
      end: '— 已加载全部 —',
    },
    detail: {
      empty: '请选择一条记录',
      emptyTitle: '未选择记录',
      notFound: '未找到该记录。',
      durationLabel: '时长 {value}',
      turnsLabel: '{n} 轮',
      modelPrefix: 'model: {model}',
      panes: {
        turns: '对话内容',
        summary: '摘要',
      },
      turnsEmpty: '无对话数据',
      bubbleWho: {
        user: 'USER',
        bot: 'BOT',
      },
    },
    summaryStatus: {
      ok: '已生成',
      failed: '失败',
      pending: '生成中',
    },
    summary: {
      pendingHint: '摘要生成中…',
      failedTitle: '摘要生成失败',
      failedFallback: '未知错误',
      empty: '无摘要数据',
      sections: {
        intent: 'Intent',
        keyQuestions: 'Key Questions',
        actionItems: 'Action Items',
        sentiment: 'Sentiment',
      },
      sentimentNeutral: 'neutral',
    },
    rel: {
      seconds: '{n} 秒前',
      minutes: '{n} 分钟前',
      hours: '{n} 小时前',
      days: '{n} 天前',
    },
    duration: '{m}m {s}s',
    errors: {
      load: '加载失败: {msg}',
      loadMore: '加载更多失败: {msg}',
      detail: '详情加载失败: {msg}',
    },
  },
  debug: {
    intro: '原始 EventBroadcaster 事件流 (最近 1000 条). 业务演示通常不需要看这些, 留给排查用.',
    empty: '尚无事件',
    rawMode: '原始模式',
  },
};
