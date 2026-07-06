// English (en) — admin SPA translation bundle.
//
// Key tree mirrors zh-CN.js exactly; only values differ. UI column names
// that are already English in zh-CN (Caller / Outcome / Engine / Demo /
// Started (UTC) / Duration / Summary / ID / Label / Lang / Voice ID, etc.)
// stay as-is here.

export default {
  common: {
    unknown: "(unknown)",
    dash: "—",
    online: 'Online',
    offline: 'Offline',
    refresh: 'Refresh',
    save: 'Save',
    cancel: 'Cancel',
    confirm: 'Confirm',
    delete: 'Delete',
    edit: 'Edit',
    create: 'New',
    reset: 'Reset',
    loading: 'Loading...',
    empty: 'No data',
    actions: 'Actions',
    toggleDark: 'Switch to dark',
    toggleLight: 'Switch to light',
    language: 'Language',
    yes: 'Yes',
    no: 'No',
    all: 'All',
    placeholderDash: '—',
  },

  app: {
    brand: 'Voice Bot Admin',
    sub: 'Runtime config · Scenario config',
    nav: {
      groupOverview: 'Overview',
      groupConfig: 'Configuration',
      groupCall: 'Call',
      groupAdmin: 'Administration',
      dashboard: 'Dashboard',
      history: 'History',
      web: 'Web defaults',
      phone: 'Phone defaults',
      demos: 'Scenario config',
      mcp: 'MCP Servers',
      voices: 'Voices',
      activity: 'Activity log',
      talk: 'Talk',
      monitor: 'Monitor',
      myHistory: 'My history',
      users: 'Users',
    },
    user: {
      logout: 'Sign out',
    },
  },

  login: {
    subtitle: 'Sign in to continue',
    username: 'Username',
    usernamePlaceholder: 'Enter your username',
    password: 'Password',
    passwordPlaceholder: 'Enter your password',
    submit: 'Sign in',
    errors: {
      usernameRequired: 'Please enter your username',
      passwordRequired: 'Please enter your password',
      invalidCredentials: 'Invalid username or password',
      generic: 'Sign-in failed: {msg}',
    },
  },

  setup: {
    subtitle: 'First-run · Set up admin',
    intro: 'This deployment has not been initialized yet. Create the first administrator account to continue; you will be signed in automatically.',
    username: 'Username',
    usernamePlaceholder: 'Choose an admin username',
    password: 'Password',
    passwordPlaceholder: 'Choose an admin password',
    confirm: 'Confirm password',
    confirmPlaceholder: 'Re-enter the password',
    submit: 'Create admin',
    errors: {
      usernameRequired: 'Please enter a username',
      passwordRequired: 'Please enter a password',
      passwordsMismatch: 'The two passwords do not match',
      alreadyInitialized: 'This deployment is already initialized. Please go to the login page.',
      invalidInput: 'Username and password cannot be empty.',
      generic: 'Setup failed: {msg}',
    },
  },

  dashboard: {
    title: 'Dashboard',
    subtitle: 'Live call metrics · 7s polling',
    updatedAt: '· Updated at {time}',
    statusOnline: 'Metrics online',
    statusFailed: 'Failed to load metrics',
    refresh: 'Refresh',
    notice: {
      header: 'Metric definitions',
      body:
        '<strong>Active calls</strong> comes from the in-process ACTIVE_SESSIONS (both phone and web are counted); ' +
        '<strong>Today / 24h series metrics</strong> (totals, average duration, outcome / engine / demo distribution, transfer rate, peak concurrency) ' +
        'are derived from DDB table <code>genaiic-voicebot-call-history</code>, where <strong>only phone calls are persisted</strong>; web sessions are not stored.',
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
      metricsTitle: 'Key metrics',
      distributionsTitle: 'Distributions',
      outcomeTitle: 'Outcome 24h (phone)',
      engineTitle: 'Engine 24h (phone)',
      demoTitle: 'Demo 24h (phone)',
      total: 'Total {n}',
      totalLabel: 'total',
      empty: 'No data',
    },
    emptyState: 'Failed to load metrics. Please try again later or click refresh in the top-right.',
    messages: {
      loadFailed: 'Failed to load dashboard metrics: {msg}',
    },
  },

  history: {
    title: 'History',
    subtitle: 'Call history browser · DDB cursor pagination · filters / CSV / Markdown export / on-demand summary',
    filters: {
      caller: 'Caller',
      callerPlaceholder: '+15550001111',
      outcome: 'Outcome',
      engine: 'Engine',
      demo: 'Demo',
      dateRange: 'Date range (UTC)',
      all: 'All',
    },
    columns: {
      startedAt: 'Started (UTC)',
      caller: 'Caller',
      outcome: 'Outcome',
      engine: 'Engine',
      demo: 'Demo',
      duration: 'Duration',
      summary: 'Summary',
      actions: 'Actions',
    },
    emptyTitle: 'No calls found',
    emptyDesc: 'No call history matches the current filters. Adjust the filters above or wait for new calls to land.',
    actions: {
      refresh: 'Refresh',
      view: 'View',
      exportCsv: 'Export CSV',
      downloadMd: 'Download MD',
      summarize: 'Summarize',
      loadMore: 'Load more',
      noMore: 'No more results',
      loadedRows: '{n} rows loaded',
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
      transferYes: 'Yes',
      transferNo: 'No',
      turns: 'Turns',
      summary: 'Summary',
      transcript: 'Transcript',
      noTurns: 'No turns data',
      noSummary: '[Not generated]',
    },
    enums: {
      outcome: {
        user_requested: 'User hung up',
        task_completed: 'Task completed',
        transferred: 'Transferred',
        timeout: 'Timeout',
        error: 'Error',
        unknown: 'Unknown',
      },
      summary: {
        ok: 'Generated',
        pending: 'Pending',
        failed: 'Generation failed',
      },
    },
    messages: {
      loadFailed: 'Failed to load: {msg}',
      loadMoreFailed: 'Failed to load more: {msg}',
      detailFailed: 'Failed to load details: {msg}',
      summaryUpdated: 'Summary updated',
      summarizeFailed: 'Failed to generate summary: {msg}',
    },
  },

  demos: {
    title: 'Scenario config',
    subtitle: 'data/<demo>/manifest.yaml + kb.md + global tool registry · auto-discovered',
    actions: {
      rescan: 'Rescan',
      reset: 'Reset',
      save: 'Save',
      startTalk: 'Start',
    },
    notice:
      'To add a new demo: <code>mkdir data/&lt;demo-id&gt;/</code> with ' +
      '<code>manifest.yaml</code> + <code>kb.md</code>, then click "Rescan". ' +
      'Tools are provided by the global registry (<code>tools/registry.py</code>); ' +
      'edit each setting in the editor on the right — saving writes to the store and takes effect on the next call.',
    columns: {
      id: 'ID',
      label: 'Label',
      lang: 'Main Language',
      kbChars: 'KB chars',
      tools: 'Tools',
      actions: 'Actions',
    },
    emptyTitle: 'No demos discovered',
    emptyDesc: 'Add a demo folder under data/ with manifest.yaml + kb.md, then rescan to pick it up.',
    listBadges: {
      tools: '{n} tools',
    },
    detail: {
      emptyTitle: 'Select a scenario',
      emptyDesc: 'Pick a scenario from the list on the left to view and edit its configuration.',
      id: 'ID',
      mainLang: 'Main language',
      kbChars: 'KB char count',
      tags: 'Tags',
      tabs: {
        info: 'Info',
        system: 'System Prompt',
        greeting: 'Greeting',
        kbIntro: 'KB intro',
        kbAck: 'KB ack',
        kb: 'KB body',
        tools: 'Tools',
        mcp: 'MCP Servers',
        translate: 'Translate',
        filler: 'Filler words',
      },
      groups: {
        info: 'Basics',
        prompts: 'Prompts',
        kb: 'Knowledge base',
        tools: 'Tools',
      },
      info: {
        hint: 'Edit the display name, default language and tags. Saving takes effect on the next new session.',
        label: 'Label',
        labelPlaceholder: 'Display name',
        lang: 'Default language',
        langPlaceholder: 'Select a default language',
        tags: 'Tags',
      },
      langField: {
        hint: 'Edit the text per language. Saving replaces this field for all listed languages.',
        addLang: 'Add a language',
        empty: 'No content yet — add a language to start.',
      },
      kbEditWarning:
        'Only the first 500 characters of each language are shown here. Saving replaces the ENTIRE knowledge-base body with what is shown — do not save unless you intend to overwrite the full KB.',
      kbHint: 'First 500 characters · for the full content see kb.md',
      toolsHint:
        'Select the LLM tools to enable for this demo. Saving writes back to ' +
        'the <code>tools:</code> field of <code>data/{id}/manifest.yaml</code> ' +
        'and takes effect immediately (next new session).',
      noTools: {
        header: 'No tools available',
        body:
          '<code>GET /api/admin/tools</code> returned an empty list — please check whether ' +
          '<code>tools/registry.py</code> is ready on the backend.',
      },
      mcpHint:
        'Select the MCP servers to mount for this demo. Saving writes back to ' +
        'the <code>mcp_servers:</code> field of <code>data/{id}/manifest.yaml</code> ' +
        'and takes effect on the next new session.',
      mcpDisabledTag: 'Disabled',
      mcpMissingTag: 'Missing',
      noMcp: {
        header: 'No MCP servers available',
        body:
          'No MCP servers are registered yet — add one from the ' +
          '<strong>MCP Servers</strong> page first, then come back to mount it here.',
      },
      fillerHint:
        'Configure the timeout filler words for this demo (e.g. “let me check”). ' +
        'Saving writes back to the <code>filler:</code> field of ' +
        '<code>data/{id}/manifest.yaml</code> and takes effect on the next new session.',
      filler: {
        enabled: 'Enabled',
        timeout: 'Timeout',
        probability: 'Probability',
        phrases: 'Custom filler phrases',
        phrasesHint: 'Leave empty to use the global pool for the call language.',
        unconfiguredHint: 'Falls back to the global default when unconfigured.',
      },
      asrFilter: {
        title: 'ASR filter',
        hint: 'Drop low-confidence short ASR transcripts (hallucinations) for this demo. Saving writes back to the asr_filter: field of the manifest and takes effect on the next new session.',
        enabled: 'Enabled',
        minConfidence: 'Min confidence',
        maxChars: 'Max CJK chars',
        maxWords: 'Max Latin words',
        unconfiguredHint: 'Empty = inherit the global / default ASR filter config.',
      },
      engineVoice: {
        title: 'Engine & voice',
        engine: 'Engine',
        provider: 'TTS provider',
        voice: 'Voice',
        model: 'LLM (model)',
        inheritOption: 'Inherit (follow session/global)',
        inheritHint:
          'Leave empty = follow the session/global default. The engine/voice set here wins when launching this scenario (scenario > session > global).',
      },
    },
    messages: {
      loadFailed: 'Failed to load demo list: {msg}',
      toolsLoadFailed: 'Failed to load tool registry: {msg}',
      rescanDone: 'Rescan complete; found {n} demos',
      rescanFailed: 'Rescan failed: {msg}',
      toolsSaved: 'Tools saved',
      mcpSaved: 'MCP servers saved',
      fillerSaved: 'Filler config saved',
      asrFilterSaved: 'ASR filter config saved',
      engineVoiceSaved: 'Engine & voice saved',
      infoSaved: 'Demo info saved',
      langFieldSaved: 'Saved',
      mcpLoadFailed: 'Failed to load MCP servers: {msg}',
      saveFailed: 'Save failed: {msg}',
      detailFailed: 'Failed to load details: {msg}',
    },
    translate: {
      hint:
        "Pick a target language to one-click translate this demo's localized " +
        'fields (system / greeting, etc.). The LLM generates a draft you can ' +
        'proofread below before confirming the write-back to ' +
        '<code>data/{id}/manifest.yaml</code>.',
      selectPlaceholder: 'Select a target language',
      translateBtn: 'Translate',
      optionPresent: 'present',
      optionMissing: 'missing',
      missingHint: 'This demo lacks {lang}; click Translate to generate it.',
      existsHint: '{lang} already exists; writing back needs overwrite confirmation.',
      previewTitle: 'Translation preview ({lang})',
      previewHint: 'Proofread the translations below, then click write-back.',
      sourceLabel: 'source: {lang}',
      writeBackBtn: 'Confirm write-back',
      messages: {
        empty: 'This demo has no localized fields to translate',
        translateFailed: 'Translation failed: {msg}',
        badRequest: 'Cannot translate: {msg}',
        overwriteNeeded: '{lang} already exists; click again to confirm overwrite.',
        writeBackDone: 'Wrote back {lang}',
        writeBackFailed: 'Write-back failed: {msg}',
      },
    },
  },

  web: {
    title: 'Web defaults',
    subtitle: 'Default engine, language, demo and voice for the browser /ws entry',
    alert: 'After saving, new browser sessions pick up the new defaults (refresh the page to apply). Existing sessions are unaffected.',
    routeTitle: 'Web defaults',
  },

  phone: {
    title: 'Phone defaults',
    subtitle: 'Default engine, language, demo and voice for PSTN inbound /phone/ws',
    alert: 'After saving, the next new call uses the new defaults (per-call hot-reload). Active calls are unaffected; no service restart required.',
    routeTitle: 'Phone defaults',
  },

  phoneNumbers: {
    title: 'Phone numbers (Chime Voice Connectors)',
    subtitle: 'Live from Chime — which phone number reaches which Voice Connector.',
    colVc: 'Voice Connector',
    colVcId: 'VC ID',
    colE164: 'Phone number',
    colStatus: 'Status',
    none: 'No number',
    empty: 'No Chime Voice Connectors found.',
    error: 'Could not read Chime (missing permission or not configured): {msg}',
  },

  defaultsForm: {
    sections: {
      engineDemo: 'Conversation engine and demo',
      voice: 'Voice',
      pipeline: 'Pipeline mode (LLM / TTS)',
    },
    pipelineHint: 'The LLM / TTS / MiniMax fields below are used only when engine = pipeline; nova-sonic runs end-to-end and ignores them (the voice is still selectable above).',
    polyglot: 'Polyglot',
    fields: {
      engine: 'Engine',
      lang: 'Language',
      demo: 'Demo',
      llmModel: 'LLM Model',
      ttsProvider: 'TTS Provider',
      voiceId: 'Voice ID',
      novaVoiceId: 'Nova Sonic Voice',
      minimaxModel: 'MiniMax Model',
    },
    actions: {
      reset: 'Reset',
      save: 'Save',
    },
    messages: {
      loadFailed: 'Failed to load: {msg}',
      noChanges: 'No changes',
      saved: 'Saved',
      saveFailed: 'Save failed: {msg}',
      restored: 'Restored',
    },
  },

  config: {
    asrFilter: {
      title: 'ASR filter / ASR hallucination filter',
      enabled: 'Enabled',
      minConfidence: 'Min confidence',
      maxChars: 'Max CJK chars',
      maxWords: 'Max Latin words',
      note: 'Default OFF. Applies to the three-stage pipeline only (Nova Sonic uses server-side STT). Per-demo settings override this.',
    },
  },

  mcp: {
    title: 'MCP Servers',
    subtitle: 'Global Model Context Protocol server registry · mount per demo from the Demos page',
    notice:
      'These servers are stored in the global registry and can be mounted per demo. ' +
      'Only <code>sse</code> and <code>streamable_http</code> transports are allowed ' +
      '(<code>stdio</code> is disabled for security). Header values are write-only — ' +
      'stored secrets are masked and never sent back to the browser.',
    columns: {
      id: 'ID',
      label: 'Label',
      transport: 'Transport',
      auth: 'Auth',
      url: 'URL',
      enabled: 'Enabled',
    },
    authType: {
      none: 'None',
      header: 'Header',
      sigv4: 'AWS SigV4',
    },
    emptyTitle: 'No MCP servers',
    emptyDesc: 'Register a Model Context Protocol server to mount it on demos from the Demos page.',
    actions: {
      add: 'Add server',
      test: 'Test',
    },
    enabledTag: {
      on: 'Enabled',
      off: 'Disabled',
    },
    form: {
      titleNew: 'Add MCP server',
      titleEdit: 'Edit MCP server',
      id: 'ID',
      idHint: 'Lowercase letters, digits and hyphens; 2–63 chars. Cannot be changed after creation.',
      label: 'Label',
      transport: 'Transport',
      url: 'URL',
      urlPlaceholder: 'https://example.com/mcp',
      enabled: 'Enabled',
      auth: 'Authentication',
      sigv4Hint: 'Requests are signed with AWS SigV4 at connect time using the instance IAM role. No secret is stored.',
      sigv4Service: 'Service',
      sigv4Region: 'Region',
      headers: 'Headers',
      headersHint: 'Optional HTTP headers (e.g. Authorization). Values are stored as secrets and masked on read.',
      headerKey: 'Header name',
      headerValuePlaceholder: '*** (unchanged)',
      headerValueNewPlaceholder: 'Value',
      addHeader: 'Add header',
    },
    deleteConfirm: {
      title: 'Delete MCP server',
      body: 'Delete MCP server "{id}"? This cannot be undone.',
    },
    test: {
      okTitle: 'Connected to "{id}" · {n} tools',
      okEmpty: 'Connected to "{id}", but it exposes no tools',
      failTitle: 'Failed to connect to "{id}"',
    },
    messages: {
      loadFailed: 'Failed to load MCP servers: {msg}',
      saved: 'Saved',
      saveFailed: 'Save failed: {msg}',
      deleted: 'Deleted',
      deleteFailed: 'Delete failed: {msg}',
      deleteRefused: 'Cannot delete "{id}" — still mounted by demos: {demos}. Unmount it there first.',
      testFailed: 'Test failed: {msg}',
    },
  },

  voices: {
    title: 'Voice registry',
    subtitle: 'Global editable voice registry · MiniMax / Polly / Nova Sonic · used by Talk & demo pickers',
    notice:
      'Voices are stored in a global registry keyed by <code>(provider, voice id)</code>. ' +
      'Adding a voice here makes it selectable in Talk and the demo / defaults pickers without a redeploy. ' +
      'When the registry table is absent the bot falls back to the built-in voice constants.',
    providers: {
      minimax: 'MiniMax',
      polly: 'Amazon Polly',
      novaSonic: 'Nova Sonic',
    },
    columns: {
      voiceId: 'Voice ID',
      label: 'Label',
      gender: 'Gender',
      language: 'Language / locale',
      boost: 'Boost',
      engine: 'Engine',
      polyglot: 'Polyglot',
    },
    fields: {
      voice_id: 'Voice ID',
      label: 'Label',
      gender: 'Gender',
      language: 'Language',
      locale: 'Locale',
      lang_label: 'Language label',
      boost: 'Boost',
      engine: 'Engine',
      polyglot: 'Polyglot',
    },
    gender: {
      male: 'Male',
      female: 'Female',
      neutral: 'Neutral',
    },
    emptyTitle: 'No voices',
    emptyDesc: 'Add a voice for this provider to make it selectable in Talk and the demo pickers.',
    actions: {
      add: 'Add voice',
    },
    form: {
      titleNew: 'Add voice',
      titleEdit: 'Edit voice',
      voiceIdPlaceholder: 'e.g. moss_audio_xxxx / Joanna / matthew',
    },
    deleteConfirm: {
      title: 'Delete voice',
      body: 'Delete voice "{id}"? Active calls using it fall back to the provider default. This cannot be undone.',
    },
    messages: {
      loadFailed: 'Failed to load voices: {msg}',
      saved: 'Saved',
      saveFailed: 'Save failed: {msg}',
      deleted: 'Deleted',
      deleteFailed: 'Delete failed: {msg}',
    },
  },

  activity: {
    title: 'Activity log',
    subtitle: 'Admin operations audit · newest first · filter by actor / type / date · sanitized detail',
    filters: {
      actor: 'Actor',
      actorPlaceholder: 'username',
      type: 'Type',
      dateRange: 'Date range (UTC)',
      all: 'All',
    },
    columns: {
      time: 'Time (UTC)',
      actor: 'Actor',
      type: 'Type',
      target: 'Target',
      status: 'Status',
      actions: 'Actions',
    },
    emptyTitle: 'No activity',
    emptyDesc: 'No audit rows match the current filters. Adjust the filters above or wait for new admin actions.',
    actions: {
      refresh: 'Refresh',
      view: 'View',
      loadMore: 'Load more',
      noMore: 'No more results',
      loadedRows: '{n} rows loaded',
    },
    detail: {
      titlePrefix: '{type}',
      time: 'Time (UTC)',
      actor: 'Actor',
      type: 'Type',
      target: 'Target',
      status: 'Status',
      error: 'Error',
      detailMap: 'Detail',
      noDetail: 'No detail recorded',
    },
    types: {
      login: 'Sign in',
      logout: 'Sign out',
      'demo-edit': 'Edit scenario',
      'mcp-upsert': 'Save MCP server',
      'mcp-delete': 'Delete MCP server',
      'config-web': 'Update web defaults',
      'config-phone': 'Update phone defaults',
      'user-create': 'Create user',
      'user-update': 'Update user',
      'user-delete': 'Delete user',
      'voice-create': 'Create voice',
      'voice-update': 'Update voice',
      'voice-delete': 'Delete voice',
      'call-start': 'Call started',
      'call-end': 'Call ended',
    },
    messages: {
      loadFailed: 'Failed to load: {msg}',
      loadMoreFailed: 'Failed to load more: {msg}',
    },
  },

  historySummary: {
    moreFields: 'more fields ({n})',
  },

  users: {
    title: 'User management',
    subtitle: 'JWT-session accounts · roles + password reset + enable/disable',
    emptyTitle: 'No users',
    emptyDesc: 'Create the first user account to grant access to the console.',
    actions: {
      add: 'New user',
      makeAdmin: 'Make admin',
      makeUser: 'Make user',
      resetPw: 'Reset password',
      enable: 'Enable',
      disable: 'Disable',
    },
    columns: {
      username: 'Username',
      role: 'Role',
      status: 'Status',
      createdAt: 'Created',
    },
    roles: {
      admin: 'Administrator',
      user: 'User',
    },
    status: {
      active: 'Active',
      disabled: 'Disabled',
    },
    form: {
      titleNew: 'Create user',
      titleResetPw: 'Reset password · {username}',
      username: 'Username',
      usernameHint: 'Letters, digits, dot, hyphen and underscore; 2 to 64 characters.',
      password: 'Password',
      newPassword: 'New password',
      passwordPlaceholder: 'Enter a password',
      role: 'Role',
    },
    deleteConfirm: {
      title: 'Delete user',
      body: 'Delete user "{username}"? This cannot be undone.',
    },
    messages: {
      loadFailed: 'Failed to load users: {msg}',
      created: 'User "{username}" created',
      createFailed: 'Create failed: {msg}',
      roleChanged: 'Role of "{username}" changed to {role}',
      pwReset: 'Password for "{username}" reset',
      enabled: 'User "{username}" enabled',
      disabled: 'User "{username}" disabled',
      updateFailed: 'Update failed: {msg}',
      deleted: 'User "{username}" deleted',
      deleteFailed: 'Delete failed: {msg}',
    },
    guestLink: {
      button: 'Generate guest link',
      title: 'Generate temporary guest link',
      ttl: 'Valid for',
      ttlOption: '{min} minutes',
      scenario: 'Scenario (optional)',
      engine: 'Engine',
      lang: 'Language',
      provider: 'TTS provider',
      voice: 'Voice',
      copy: 'Copy',
      copied: 'Link copied',
      copyFailed: 'Copy failed — copy it manually',
      expiry: 'Expires at: {time}',
      failed: 'Generation failed: {msg}',
    },
  },

  // Temporary guest-link landing page (tech_design §3.1).
  guest: {
    validating: 'Validating guest link…',
    redirecting: 'Entering the Talk demo…',
    failed: 'This link is invalid or has expired. Please ask the admin for a new one.',
  },

  // --- Call views merged from the demo SPA (tech_design §3) ---
  // talk / monitor / debug come from the demo views verbatim; myHistory is
  // the demo's per-user call-history view (renamed from `history` to avoid
  // colliding with admin's full HistoryView `history` namespace).
  talk: {
    actions: {
      summarize: 'Generate summary (Markdown)',
      debug: 'Debug / event stream',
    },
    status: {
      ready: 'Ready',
      connecting: 'Connecting…',
      recording: 'Recording…',
    },
    button: {
      start: 'Start',
      connecting: 'Connecting…',
      stop: 'Stop',
    },
    selectors: {
      engine: 'Engine',
      language: 'Language',
      provider: 'Provider',
      voice: 'Voice',
      model: 'LLM',
    },
    defaultsHint: 'Engine / language / scenario are configured in Admin. To change defaults, go to {adminLink}',
    defaultsHintAdminLabel: 'Admin',
    ptt: {
      toggle: 'Push-to-talk mode',
      holdToTalk: 'Hold to talk',
      holding: 'Listening…',
      spaceHint: 'Or hold the spacebar to talk',
    },
    bubbles: {
      empty: 'Click the center button to start the conversation',
      whoUser: 'Me',
      whoBot: 'Bot',
      partial: 'Live',
    },
    drawerTitle: 'Event stream (debug)',
    drawerClose: 'Close',
    summary: {
      title: 'Conversation summary',
      generating: 'Generating…',
      failed: 'Summary failed: {msg}',
    },
    errors: {
      loadConfig: 'Failed to load config: {msg}',
      mic: 'Microphone init failed: {msg}',
      ws: 'WebSocket connection failed',
      start: 'Start failed: {msg}',
    },
  },
  monitor: {
    status: {
      online: 'Online',
      ended: 'Ended',
      noCalls: 'No calls',
      idle: 'Idle',
    },
    refreshTooltip: 'Refresh call list now',
    empty: {
      noActive: 'No active calls',
      noActiveHint: 'Place a PSTN call or start a web session on /talk to see it here.',
      noSelection: 'Select a call',
      noSelectionHint: 'Choose a live call on the left to stream its events.',
      noEvents: 'Waiting for events…',
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
      refresh: 'Refresh failed: {msg}',
      ws: 'Monitor WebSocket error',
      callEnded: 'Call {id}… ended',
    },
  },
  myHistory: {
    filter: {
      refreshTooltip: 'Refresh history now',
      counter: '{filtered} / {total} shown',
    },
    window: {
      all: 'All',
      today: 'Today',
      last7d: 'Last 7 days',
      last30d: 'Last 30 days',
    },
    list: {
      empty: 'No call history',
      emptyTitle: 'No calls yet',
      loadMore: 'Load more',
      end: '— All loaded —',
    },
    detail: {
      empty: 'Select a record',
      emptyTitle: 'No record selected',
      notFound: 'Record not found.',
      durationLabel: 'Duration {value}',
      turnsLabel: '{n} turns',
      modelPrefix: 'model: {model}',
      panes: {
        turns: 'Conversation',
        summary: 'Summary',
      },
      turnsEmpty: 'No conversation data',
      bubbleWho: {
        user: 'USER',
        bot: 'BOT',
      },
    },
    summaryStatus: {
      ok: 'Generated',
      failed: 'Failed',
      pending: 'Generating',
    },
    summary: {
      pendingHint: 'Summary generating…',
      failedTitle: 'Summary generation failed',
      failedFallback: 'Unknown error',
      empty: 'No summary data',
      sections: {
        intent: 'Intent',
        keyQuestions: 'Key Questions',
        actionItems: 'Action Items',
        sentiment: 'Sentiment',
      },
      sentimentNeutral: 'neutral',
    },
    rel: {
      seconds: '{n}s ago',
      minutes: '{n}m ago',
      hours: '{n}h ago',
      days: '{n}d ago',
    },
    duration: '{m}m {s}s',
    errors: {
      load: 'Load failed: {msg}',
      loadMore: 'Load more failed: {msg}',
      detail: 'Detail load failed: {msg}',
    },
  },
  debug: {
    intro: 'Raw EventBroadcaster stream (last 1000 events). Not needed for normal demos — kept for troubleshooting.',
    empty: 'No events yet',
    rawMode: 'Raw mode',
  },
};
