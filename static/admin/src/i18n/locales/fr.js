// Français (fr) — admin SPA translation bundle.
//
// Key tree mirrors zh-CN.js exactly; only values differ.
// Français standard, vouvoiement.

export default {
  common: {
    unknown: "(inconnu)",
    dash: "—",
    online: 'En ligne',
    offline: 'Hors ligne',
    refresh: 'Actualiser',
    save: 'Enregistrer',
    cancel: 'Annuler',
    confirm: 'Confirmer',
    delete: 'Supprimer',
    edit: 'Modifier',
    create: 'Créer',
    reset: 'Réinitialiser',
    loading: 'Chargement...',
    empty: 'Aucune donnée',
    actions: 'Actions',
    toggleDark: 'Passer en mode sombre',
    toggleLight: 'Passer en mode clair',
    language: 'Langue',
    yes: 'Oui',
    no: 'Non',
    all: 'Tous',
    placeholderDash: '—',
  },

  app: {
    brand: 'Voice Bot Admin',
    sub: 'Configuration d’exécution · Configuration des scénarios',
    nav: {
      groupOverview: 'Vue d’ensemble',
      groupConfig: 'Configuration',
      groupCall: 'Appel',
      groupAdmin: 'Administration',
      dashboard: 'Tableau de bord',
      history: 'Historique',
      web: 'Valeurs par défaut Web',
      phone: 'Valeurs par défaut Phone',
      demos: 'Configuration des scénarios',
      mcp: 'Serveurs MCP',
      voices: 'Voix',
      activity: 'Journal d\'activité',
      talk: 'Parler',
      monitor: 'Superviser',
      myHistory: 'Mon historique',
      users: 'Utilisateurs',
    },
    user: {
      logout: 'Se déconnecter',
    },
  },

  login: {
    subtitle: 'Connectez-vous pour continuer',
    username: 'Nom d’utilisateur',
    usernamePlaceholder: 'Saisissez votre nom d’utilisateur',
    password: 'Mot de passe',
    passwordPlaceholder: 'Saisissez votre mot de passe',
    submit: 'Se connecter',
    errors: {
      usernameRequired: 'Saisissez votre nom d’utilisateur',
      passwordRequired: 'Saisissez votre mot de passe',
      invalidCredentials: 'Nom d’utilisateur ou mot de passe incorrect',
      generic: 'Échec de la connexion : {msg}',
    },
  },

  setup: {
    subtitle: 'Première utilisation · Configurer l’administrateur',
    intro: 'Ce déploiement n’a pas encore été initialisé. Créez le premier compte administrateur pour continuer ; vous serez connecté automatiquement.',
    username: 'Nom d’utilisateur',
    usernamePlaceholder: 'Choisissez un nom d’utilisateur administrateur',
    password: 'Mot de passe',
    passwordPlaceholder: 'Choisissez un mot de passe administrateur',
    confirm: 'Confirmer le mot de passe',
    confirmPlaceholder: 'Saisissez à nouveau le mot de passe',
    submit: 'Créer l’administrateur',
    errors: {
      usernameRequired: 'Saisissez un nom d’utilisateur',
      passwordRequired: 'Saisissez un mot de passe',
      passwordsMismatch: 'Les deux mots de passe ne correspondent pas',
      alreadyInitialized: 'Ce déploiement est déjà initialisé. Veuillez aller à la page de connexion.',
      invalidInput: 'Le nom d’utilisateur et le mot de passe ne peuvent pas être vides.',
      generic: 'Échec de la création : {msg}',
    },
  },

  dashboard: {
    title: 'Tableau de bord',
    subtitle: 'Métriques d’appels en direct · sondage 7 s',
    updatedAt: '· Mis à jour à {time}',
    statusOnline: 'Métriques en ligne',
    statusFailed: 'Échec de récupération des métriques',
    refresh: 'Actualiser',
    notice: {
      header: 'Définitions des indicateurs',
      body:
        '<strong>Active calls</strong> provient des ACTIVE_SESSIONS internes au processus (phone et web sont comptabilisés). ' +
        '<strong>Les indicateurs de la série Today / 24h</strong> (totaux, durée moyenne, répartition Outcome / Engine / Demo, taux de transfert, pic de concurrence) ' +
        's’appuient sur la table DDB <code>genaiic-voicebot-call-history</code> ; <strong>seuls les appels phone sont persistés</strong>, les sessions web ne le sont pas.',
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
      metricsTitle: 'Indicateurs clés',
      distributionsTitle: 'Répartitions',
      outcomeTitle: 'Outcome 24h (phone)',
      engineTitle: 'Engine 24h (phone)',
      demoTitle: 'Demo 24h (phone)',
      total: 'Total {n}',
      totalLabel: 'total',
      empty: 'Aucune donnée',
    },
    emptyState: 'Échec du chargement des métriques. Veuillez réessayer plus tard ou cliquer sur Actualiser en haut à droite.',
    messages: {
      loadFailed: 'Échec du chargement des métriques du tableau de bord : {msg}',
    },
  },

  history: {
    title: 'Historique',
    subtitle: 'Explorateur de l’historique des appels · pagination par curseur DDB · filtres / export CSV / Markdown / résumé à la demande',
    filters: {
      caller: 'Caller',
      callerPlaceholder: '+15550001111',
      outcome: 'Outcome',
      engine: 'Engine',
      demo: 'Demo',
      dateRange: 'Plage de dates (UTC)',
      all: 'Tous',
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
    emptyTitle: 'Aucun appel trouvé',
    emptyDesc: 'Aucun historique d\'appels ne correspond aux filtres actuels. Ajustez les filtres ci-dessus ou attendez l\'arrivée de nouveaux appels.',
    actions: {
      refresh: 'Actualiser',
      view: 'Afficher',
      exportCsv: 'Exporter en CSV',
      downloadMd: 'Télécharger le MD',
      summarize: 'Générer un résumé',
      loadMore: 'Charger plus',
      noMore: 'Aucun autre résultat',
      loadedRows: '{n} lignes chargées',
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
      transferYes: 'Oui',
      transferNo: 'Non',
      turns: 'Turns',
      summary: 'Summary',
      transcript: 'Transcript',
      noTurns: 'Aucune donnée turns',
      noSummary: '[Non généré]',
    },
    enums: {
      outcome: {
        user_requested: 'Raccroché par l’utilisateur',
        task_completed: 'Tâche terminée',
        transferred: 'Transférée',
        timeout: 'Délai dépassé',
        error: 'Erreur',
        unknown: 'Inconnu',
      },
      summary: {
        ok: 'Généré',
        pending: 'En attente',
        failed: 'Échec de génération',
      },
    },
    messages: {
      loadFailed: 'Échec du chargement : {msg}',
      loadMoreFailed: 'Échec du chargement supplémentaire : {msg}',
      detailFailed: 'Échec du chargement des détails : {msg}',
      summaryUpdated: 'Résumé mis à jour',
      summarizeFailed: 'Échec de génération du résumé : {msg}',
    },
  },

  demos: {
    title: 'Configuration des scénarios',
    subtitle: 'data/<demo>/manifest.yaml + kb.md + bibliothèque d’outils globale · découverte automatique',
    actions: {
      rescan: 'Rescanner',
      reset: 'Réinitialiser',
      save: 'Enregistrer',
      startTalk: 'Démarrer',
    },
    notice:
      'Pour ajouter une nouvelle démo : <code>mkdir data/&lt;demo-id&gt;/</code> contenant ' +
      '<code>manifest.yaml</code> + <code>kb.md</code>, puis cliquez sur « Rescanner » pour l’activer. ' +
      'Les outils sont fournis par le registre global (<code>tools/registry.py</code>) ; ' +
      'modifiez chaque réglage dans l’éditeur de droite — l’enregistrement écrit dans la base et prend effet au prochain appel.',
    columns: {
      id: 'ID',
      label: 'Label',
      lang: 'Main Language',
      kbChars: 'Caractères de KB',
      tools: 'Tools',
      actions: 'Actions',
    },
    emptyTitle: 'Aucune démo découverte',
    emptyDesc: 'Créez un dossier de démo dans data/ avec manifest.yaml + kb.md, puis relancez le scan pour le prendre en compte.',
    listBadges: {
      tools: '{n} outils',
    },
    detail: {
      emptyTitle: 'Sélectionnez un scénario',
      emptyDesc: 'Choisissez un scénario dans la liste de gauche pour afficher et modifier sa configuration.',
      id: 'ID',
      mainLang: 'Langue principale',
      kbChars: 'Nombre de caractères de KB',
      tags: 'Étiquettes',
      tabs: {
        info: 'Infos',
        system: 'System Prompt',
        greeting: 'Greeting',
        kbIntro: 'Intro KB',
        kbAck: 'Ack KB',
        kb: 'Corps de KB',
        tools: 'Tools',
        mcp: 'Serveurs MCP',
        translate: 'Traduire',
        filler: 'Mots de remplissage',
      },
      groups: {
        info: 'Général',
        prompts: 'Prompts',
        kb: 'Base de connaissances',
        tools: 'Outils',
      },
      info: {
        hint: 'Modifiez le nom affiché, la langue par défaut et les étiquettes. La sauvegarde prend effet à la prochaine nouvelle session.',
        label: 'Étiquette',
        labelPlaceholder: 'Nom affiché',
        lang: 'Langue par défaut',
        langPlaceholder: 'Sélectionnez une langue par défaut',
        tags: 'Étiquettes',
      },
      langField: {
        hint: 'Modifiez le texte par langue. La sauvegarde remplace ce champ pour toutes les langues listées.',
        addLang: 'Ajouter une langue',
        empty: 'Pas encore de contenu — ajoutez une langue pour commencer.',
      },
      kbEditWarning:
        'Seuls les 500 premiers caractères de chaque langue sont affichés ici. La sauvegarde remplace la TOTALITÉ du corps de la base de connaissances par ce qui est affiché ; ne sauvegardez pas sauf si vous voulez écraser toute la KB.',
      kbHint: 'Premiers 500 caractères · pour le contenu complet, consultez directement kb.md',
      toolsHint:
        'Sélectionnez les outils LLM à activer pour cette démo. L’enregistrement écrit dans ' +
        'le champ <code>tools:</code> de <code>data/{id}/manifest.yaml</code> ' +
        'et prend effet immédiatement (à la prochaine nouvelle session).',
      noTools: {
        header: 'Aucun outil disponible',
        body:
          '<code>GET /api/admin/tools</code> a renvoyé une liste vide — veuillez vérifier que ' +
          '<code>tools/registry.py</code> est bien en place côté backend.',
      },
      mcpHint:
        'Sélectionnez les serveurs MCP à monter pour cette démo. L’enregistrement écrit dans ' +
        'le champ <code>mcp_servers:</code> de <code>data/{id}/manifest.yaml</code> ' +
        'et prend effet à la prochaine nouvelle session.',
      mcpDisabledTag: 'Désactivé',
      mcpMissingTag: 'Introuvable',
      noMcp: {
        header: 'Aucun serveur MCP disponible',
        body:
          'Aucun serveur MCP n’est encore enregistré — ajoutez-en un d’abord depuis la page ' +
          '<strong>Serveurs MCP</strong>, puis revenez ici pour le monter.',
      },
      fillerHint:
        'Configurez les mots de remplissage d’attente pour cette démo (p. ex. « laissez-moi vérifier »). ' +
        'L’enregistrement écrit dans le champ <code>filler:</code> de ' +
        '<code>data/{id}/manifest.yaml</code> et prend effet à la prochaine nouvelle session.',
      filler: {
        enabled: 'Activé',
        timeout: 'Délai d’attente',
        probability: 'Probabilité',
        phrases: 'Mots de remplissage personnalisés',
        phrasesHint: 'Laissez vide pour utiliser le pool global de la langue de l’appel.',
        unconfiguredHint: 'En l’absence de configuration, la valeur par défaut globale est utilisée.',
      },
      asrFilter: {
        title: 'Filtre ASR',
        hint: 'Supprime les transcriptions ASR courtes et peu fiables (hallucinations) pour ce démo. L’enregistrement écrit dans le champ asr_filter: du manifeste et prend effet à la prochaine nouvelle session.',
        enabled: 'Activé',
        minConfidence: 'Confiance minimale',
        maxChars: 'Caractères CJK max',
        maxWords: 'Mots latins max',
        unconfiguredHint: 'Vide = hérite de la configuration globale / par défaut du filtre ASR.',
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
      loadFailed: 'Échec du chargement de la liste des démos : {msg}',
      toolsLoadFailed: 'Échec du chargement de la bibliothèque d’outils : {msg}',
      rescanDone: 'Scan terminé, {n} démo(s) détectée(s)',
      rescanFailed: 'Échec du scan : {msg}',
      toolsSaved: 'Outils enregistrés',
      mcpSaved: 'Serveurs MCP enregistrés',
      fillerSaved: 'Configuration des mots de remplissage enregistrée',
      asrFilterSaved: 'Configuration du filtre ASR enregistrée',
      engineVoiceSaved: 'Engine & voice saved',
      infoSaved: 'Infos du démo enregistrées',
      langFieldSaved: 'Enregistré',
      mcpLoadFailed: 'Échec du chargement des serveurs MCP : {msg}',
      saveFailed: 'Échec de l’enregistrement : {msg}',
      detailFailed: 'Échec du chargement des détails : {msg}',
    },
    translate: {
      hint:
        'Choisissez une langue cible pour traduire en un clic les champs ' +
        'localisés de cette démo (system / greeting, etc.). Le LLM génère un ' +
        'brouillon que vous pouvez relire ci-dessous avant de confirmer ' +
        'l’écriture dans <code>data/{id}/manifest.yaml</code>.',
      selectPlaceholder: 'Choisir une langue cible',
      translateBtn: 'Traduire',
      optionPresent: 'présente',
      optionMissing: 'absente',
      missingHint: 'Cette démo n’a pas {lang} ; cliquez sur Traduire pour le générer.',
      existsHint: '{lang} existe déjà ; l’écriture nécessite une confirmation d’écrasement.',
      previewTitle: 'Aperçu de la traduction ({lang})',
      previewHint: 'Relisez les traductions ci-dessous, puis cliquez sur écrire.',
      sourceLabel: 'source : {lang}',
      writeBackBtn: 'Confirmer l’écriture',
      messages: {
        empty: 'Cette démo n’a aucun champ localisé à traduire',
        translateFailed: 'Échec de la traduction : {msg}',
        badRequest: 'Traduction impossible : {msg}',
        overwriteNeeded: '{lang} existe déjà ; cliquez à nouveau pour confirmer l’écrasement.',
        writeBackDone: '{lang} écrit',
        writeBackFailed: 'Échec de l’écriture : {msg}',
      },
    },
  },

  web: {
    title: 'Configuration par défaut Web',
    subtitle: 'Moteur, langue, démo et voix par défaut pour le point d’entrée navigateur /ws',
    alert: 'Après l’enregistrement, les nouvelles sessions navigateur prennent en compte les nouveaux paramètres (rechargez la page pour les obtenir). Les sessions ouvertes ne sont pas affectées.',
    routeTitle: 'Valeurs par défaut Web',
  },

  phone: {
    title: 'Configuration par défaut Phone',
    subtitle: 'Moteur, langue, démo et voix par défaut pour les appels PSTN entrants /phone/ws',
    alert: 'Après l’enregistrement, le prochain nouvel appel utilise les nouveaux paramètres (hot-reload par appel). Les appels en cours restent inchangés ; aucun redémarrage de service n’est nécessaire.',
    routeTitle: 'Valeurs par défaut Phone',
  },

  phoneNumbers: {
    title: 'Numéros de téléphone (Chime Voice Connectors)',
    subtitle: 'En direct depuis Chime — quel numéro atteint quel Voice Connector.',
    colVc: 'Voice Connector',
    colVcId: 'ID VC',
    colE164: 'Numéro de téléphone',
    colStatus: 'Statut',
    none: 'Aucun numéro',
    empty: 'Aucun Chime Voice Connector trouvé.',
    error: 'Impossible de lire Chime (permission manquante ou non configuré) : {msg}',
  },

  defaultsForm: {
    sections: {
      engineDemo: 'Moteur de conversation et démo',
      voice: 'Voix',
      pipeline: 'Mode Pipeline (LLM / TTS)',
    },
    pipelineHint: 'Les champs LLM / TTS / MiniMax ci-dessous ne sont utilisés que lorsque engine = pipeline ; nova-sonic fonctionne de bout en bout et ne les lit pas (la voix reste sélectionnable ci-dessus).',
    polyglot: 'Polyglotte',
    fields: {
      engine: 'Engine',
      lang: 'Language',
      demo: 'Demo',
      llmModel: 'LLM Model',
      ttsProvider: 'TTS Provider',
      voiceId: 'Voice ID',
      novaVoiceId: 'Voix Nova Sonic',
      minimaxModel: 'MiniMax Model',
    },
    actions: {
      reset: 'Réinitialiser',
      save: 'Enregistrer',
    },
    messages: {
      loadFailed: 'Échec du chargement : {msg}',
      noChanges: 'Aucune modification',
      saved: 'Enregistré',
      saveFailed: 'Échec de l’enregistrement : {msg}',
      restored: 'Réinitialisé',
    },
  },

  config: {
    asrFilter: {
      title: 'Filtre ASR / ASR hallucination filter',
      enabled: 'Activé',
      minConfidence: 'Confiance minimale',
      maxChars: 'Caractères CJK max',
      maxWords: 'Mots latins max',
      note: 'Désactivé par défaut. S\'applique uniquement au pipeline à trois étages (Nova Sonic utilise la STT côté serveur). Les réglages par démo prévalent sur cette valeur.',
    },
  },

  mcp: {
    title: 'Serveurs MCP',
    subtitle: 'Registre global des serveurs Model Context Protocol · à monter par démo depuis la page Démos',
    notice:
      'Ces serveurs sont stockés dans le registre global et peuvent être montés par démo. ' +
      'Seuls les transports <code>sse</code> et <code>streamable_http</code> sont autorisés ' +
      '(<code>stdio</code> est désactivé pour des raisons de sécurité). Les valeurs d’en-tête sont en écriture seule : ' +
      'les secrets stockés sont masqués et ne sont jamais renvoyés au navigateur.',
    columns: {
      id: 'ID',
      label: 'Label',
      transport: 'Transport',
      auth: 'Authentification',
      url: 'URL',
      enabled: 'Activé',
    },
    authType: {
      none: 'Aucune',
      header: 'Header',
      sigv4: 'AWS SigV4',
    },
    emptyTitle: 'Aucun serveur MCP',
    emptyDesc: 'Enregistrez un serveur Model Context Protocol pour le monter sur les démos depuis la page Démos.',
    actions: {
      add: 'Ajouter un serveur',
      test: 'Tester',
    },
    enabledTag: {
      on: 'Activé',
      off: 'Désactivé',
    },
    form: {
      titleNew: 'Ajouter un serveur MCP',
      titleEdit: 'Modifier le serveur MCP',
      id: 'ID',
      idHint: 'Lettres minuscules, chiffres et traits d’union ; 2 à 63 caractères. Non modifiable après création.',
      label: 'Label',
      transport: 'Transport',
      url: 'URL',
      urlPlaceholder: 'https://example.com/mcp',
      enabled: 'Activé',
      auth: 'Authentification',
      sigv4Hint: 'Les requêtes sont signées avec AWS SigV4 à la connexion via le rôle IAM de l’instance. Aucun secret n’est stocké.',
      sigv4Service: 'Service',
      sigv4Region: 'Region',
      headers: 'Headers',
      headersHint: 'En-têtes HTTP facultatifs (par ex. Authorization). Les valeurs sont stockées comme des secrets et masquées à la lecture.',
      headerKey: 'Nom de l’en-tête',
      headerValuePlaceholder: '*** (inchangé)',
      headerValueNewPlaceholder: 'Valeur',
      addHeader: 'Ajouter un en-tête',
    },
    deleteConfirm: {
      title: 'Supprimer le serveur MCP',
      body: 'Supprimer le serveur MCP « {id} » ? Cette action est irréversible.',
    },
    test: {
      okTitle: 'Connecté à « {id} » · {n} outils',
      okEmpty: 'Connecté à « {id} », mais aucun outil n’est exposé',
      failTitle: 'Échec de la connexion à « {id} »',
    },
    messages: {
      loadFailed: 'Échec du chargement des serveurs MCP : {msg}',
      saved: 'Enregistré',
      saveFailed: 'Échec de l’enregistrement : {msg}',
      deleted: 'Supprimé',
      deleteFailed: 'Échec de la suppression : {msg}',
      deleteRefused: 'Impossible de supprimer « {id} » — encore monté par les démos : {demos}. Démontez-le d’abord à cet endroit.',
      testFailed: 'Échec du test : {msg}',
    },
  },

  voices: {
    title: 'Registre des voix',
    subtitle: 'Registre des voix global et modifiable · MiniMax / Polly / Nova Sonic · utilisé par les sélecteurs Appel et scénarios',
    notice:
      'Les voix sont stockées dans un registre global avec la clé <code>(fournisseur, ID de voix)</code>. ' +
      'Ajouter une voix ici la rend sélectionnable dans Appel et dans les sélecteurs de scénarios / valeurs par défaut sans redéploiement. ' +
      'Lorsque la table du registre est absente, le bot se rabat sur les constantes de voix intégrées.',
    providers: {
      minimax: 'MiniMax',
      polly: 'Amazon Polly',
      novaSonic: 'Nova Sonic',
    },
    columns: {
      voiceId: 'ID de voix',
      label: 'Libellé',
      gender: 'Genre',
      language: 'Langue / paramètres régionaux',
      boost: 'Renfort',
      engine: 'Moteur',
      polyglot: 'Polyglotte',
    },
    fields: {
      voice_id: 'ID de voix',
      label: 'Libellé',
      gender: 'Genre',
      language: 'Langue',
      locale: 'Paramètres régionaux',
      lang_label: 'Libellé de langue',
      boost: 'Renfort',
      engine: 'Moteur',
      polyglot: 'Polyglotte',
    },
    gender: {
      male: 'Masculin',
      female: 'Féminin',
      neutral: 'Neutre',
    },
    emptyTitle: 'Aucune voix',
    emptyDesc: 'Ajoutez une voix pour ce fournisseur afin de la rendre sélectionnable dans Appel et les sélecteurs de scénarios.',
    actions: {
      add: 'Ajouter une voix',
    },
    form: {
      titleNew: 'Ajouter une voix',
      titleEdit: 'Modifier la voix',
      voiceIdPlaceholder: 'ex. moss_audio_xxxx / Joanna / matthew',
    },
    deleteConfirm: {
      title: 'Supprimer la voix',
      body: 'Supprimer la voix « {id} » ? Les appels actifs qui l\'utilisent se rabattront sur la voix par défaut du fournisseur. Cette action est irréversible.',
    },
    messages: {
      loadFailed: 'Échec du chargement des voix : {msg}',
      saved: 'Enregistré',
      saveFailed: 'Échec de l\'enregistrement : {msg}',
      deleted: 'Supprimé',
      deleteFailed: 'Échec de la suppression : {msg}',
    },
  },

  activity: {
    title: 'Journal d\'activité',
    subtitle: 'Audit des opérations d\'administration · plus récentes d\'abord · filtre par acteur / type / date · détail nettoyé',
    filters: {
      actor: 'Acteur',
      actorPlaceholder: 'utilisateur',
      type: 'Type',
      dateRange: 'Plage de dates (UTC)',
      all: 'Tous',
    },
    columns: {
      time: 'Heure (UTC)',
      actor: 'Acteur',
      type: 'Type',
      target: 'Cible',
      status: 'Statut',
      actions: 'Actions',
    },
    emptyTitle: 'Aucune activité',
    emptyDesc: 'Aucune ligne d\'audit ne correspond aux filtres actuels. Ajustez les filtres ou attendez de nouvelles actions d\'administration.',
    actions: {
      refresh: 'Actualiser',
      view: 'Voir',
      loadMore: 'Charger plus',
      noMore: 'Aucun autre résultat',
      loadedRows: '{n} lignes chargées',
    },
    detail: {
      titlePrefix: '{type}',
      time: 'Heure (UTC)',
      actor: 'Acteur',
      type: 'Type',
      target: 'Cible',
      status: 'Statut',
      error: 'Erreur',
      detailMap: 'Détail',
      noDetail: 'Aucun détail enregistré',
    },
    types: {
      login: 'Connexion',
      logout: 'Déconnexion',
      'demo-edit': 'Modifier le scénario',
      'mcp-upsert': 'Enregistrer le serveur MCP',
      'mcp-delete': 'Supprimer le serveur MCP',
      'config-web': 'Mettre à jour les valeurs web',
      'config-phone': 'Mettre à jour les valeurs téléphone',
      'user-create': 'Créer un utilisateur',
      'user-update': 'Mettre à jour un utilisateur',
      'user-delete': 'Supprimer un utilisateur',
      'voice-create': 'Créer une voix',
      'voice-update': 'Mettre à jour une voix',
      'voice-delete': 'Supprimer une voix',
      'call-start': 'Appel démarré',
      'call-end': 'Appel terminé',
    },
    messages: {
      loadFailed: 'Échec du chargement : {msg}',
      loadMoreFailed: 'Échec du chargement supplémentaire : {msg}',
    },
  },

  historySummary: {
    moreFields: 'more fields ({n})',
  },

  users: {
    title: 'Gestion des utilisateurs',
    subtitle: 'Comptes à session JWT · rôles + réinitialisation du mot de passe + activer/désactiver',
    emptyTitle: 'Aucun utilisateur',
    emptyDesc: 'Créez le premier compte utilisateur pour accorder l’accès à la console.',
    actions: {
      add: 'Nouvel utilisateur',
      makeAdmin: 'Promouvoir admin',
      makeUser: 'Rétrograder utilisateur',
      resetPw: 'Réinitialiser le mot de passe',
      enable: 'Activer',
      disable: 'Désactiver',
    },
    columns: {
      username: 'Utilisateur',
      role: 'Rôle',
      status: 'Statut',
      createdAt: 'Créé',
    },
    roles: {
      admin: 'Administrateur',
      user: 'Utilisateur',
    },
    status: {
      active: 'Actif',
      disabled: 'Désactivé',
    },
    form: {
      titleNew: 'Créer un utilisateur',
      titleResetPw: 'Réinitialiser le mot de passe · {username}',
      username: 'Utilisateur',
      usernameHint: 'Lettres, chiffres, point, tiret et tiret bas ; 2 à 64 caractères.',
      password: 'Mot de passe',
      newPassword: 'Nouveau mot de passe',
      passwordPlaceholder: 'Saisir un mot de passe',
      role: 'Rôle',
    },
    deleteConfirm: {
      title: 'Supprimer l’utilisateur',
      body: 'Supprimer l’utilisateur « {username} » ? Cette action est irréversible.',
    },
    messages: {
      loadFailed: 'Échec du chargement des utilisateurs : {msg}',
      created: 'Utilisateur « {username} » créé',
      createFailed: 'Échec de la création : {msg}',
      roleChanged: 'Rôle de « {username} » changé en {role}',
      pwReset: 'Mot de passe de « {username} » réinitialisé',
      enabled: 'Utilisateur « {username} » activé',
      disabled: 'Utilisateur « {username} » désactivé',
      updateFailed: 'Échec de la mise à jour : {msg}',
      deleted: 'Utilisateur « {username} » supprimé',
      deleteFailed: 'Échec de la suppression : {msg}',
    },
    guestLink: {
      button: 'Générer un lien invité',
      title: 'Générer un lien invité temporaire',
      ttl: 'Valable',
      ttlOption: '{min} minutes',
      scenario: 'Scénario (facultatif)',
      engine: 'Moteur',
      lang: 'Langue',
      provider: 'Fournisseur TTS',
      voice: 'Voix',
      copy: 'Copier',
      copied: 'Lien copié',
      copyFailed: 'Échec de la copie ; copiez-le manuellement',
      expiry: 'Expire à : {time}',
      failed: 'Échec de la génération : {msg}',
    },
  },

  // Page d'atterrissage du lien invité temporaire (tech_design §3.1).
  guest: {
    validating: 'Validation du lien invité…',
    redirecting: 'Accès à la démo Talk…',
    failed: 'Ce lien est invalide ou a expiré. Veuillez en demander un nouveau à l\'administrateur.',
  },

  // --- Call views merged from the demo SPA (tech_design §3) ---
  // talk / monitor / debug come from the demo views verbatim; myHistory is
  // the demo's per-user call-history view (renamed from `history` to avoid
  // colliding with admin's full HistoryView `history` namespace).
  talk: {
    actions: {
      summarize: 'Générer un résumé de la conversation (Markdown)',
      debug: 'Déboguer / flux d\'événements',
    },
    status: {
      ready: 'Prêt',
      connecting: 'Connexion…',
      recording: 'Enregistrement…',
    },
    button: {
      start: 'Démarrer',
      connecting: 'Connexion…',
      stop: 'Arrêter',
    },
    selectors: {
      engine: 'Engine',
      language: 'Language',
      provider: 'Provider',
      voice: 'Voice',
      model: 'LLM',
    },
    defaultsHint: 'Le moteur / la langue / le scénario sont configurés dans Admin. Pour modifier les valeurs par défaut, veuillez accéder à {adminLink}',
    defaultsHintAdminLabel: 'Admin',
    ptt: {
      toggle: 'Mode appuyer pour parler',
      holdToTalk: 'Maintenir pour parler',
      holding: 'Écoute…',
      spaceHint: 'Ou maintenez la barre d’espace pour parler',
    },
    bubbles: {
      empty: 'Cliquez sur le bouton central pour commencer la conversation',
      whoUser: 'Moi',
      whoBot: 'Bot',
      partial: 'En direct',
    },
    drawerTitle: 'Flux d\'événements (débogage)',
    drawerClose: 'Fermer',
    summary: {
      title: 'Résumé de la conversation',
      generating: 'Génération…',
      failed: 'Échec du résumé : {msg}',
    },
    errors: {
      loadConfig: 'Échec du chargement de la configuration : {msg}',
      mic: 'Échec de l\'initialisation du micro : {msg}',
      ws: 'Échec de la connexion WebSocket',
      start: 'Échec du démarrage : {msg}',
    },
  },
  monitor: {
    status: {
      online: 'En ligne',
      ended: 'Terminé',
      noCalls: 'Aucun appel',
      idle: 'Inactif',
    },
    refreshTooltip: 'Actualiser la liste des appels',
    empty: {
      noActive: 'Aucun appel actif',
      noActiveHint: 'Appelez un numéro PSTN ou démarrez une session web sur /talk pour le voir ici.',
      noSelection: 'Sélectionnez un appel',
      noSelectionHint: 'Choisissez un appel en cours à gauche pour diffuser ses événements.',
      noEvents: 'En attente d\'événements…',
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
      refresh: 'Échec de l\'actualisation : {msg}',
      ws: 'Erreur WebSocket du moniteur',
      callEnded: 'L\'appel {id}… est terminé',
    },
  },
  myHistory: {
    filter: {
      refreshTooltip: 'Actualiser l\'historique',
      counter: '{filtered} / {total} affichés',
    },
    window: {
      all: 'Tout',
      today: 'Aujourd\'hui',
      last7d: '7 derniers jours',
      last30d: '30 derniers jours',
    },
    list: {
      empty: 'Aucun historique d\'appel',
      emptyTitle: 'Aucun appel pour l\'instant',
      loadMore: 'Charger plus',
      end: '— Tout chargé —',
    },
    detail: {
      empty: 'Sélectionnez un enregistrement',
      emptyTitle: 'Aucun enregistrement sélectionné',
      notFound: 'Enregistrement introuvable.',
      durationLabel: 'Durée {value}',
      turnsLabel: '{n} tours',
      modelPrefix: 'model: {model}',
      panes: {
        turns: 'Conversation',
        summary: 'Résumé',
      },
      turnsEmpty: 'Aucune donnée de conversation',
      bubbleWho: {
        user: 'USER',
        bot: 'BOT',
      },
    },
    summaryStatus: {
      ok: 'Généré',
      failed: 'Échec',
      pending: 'Génération',
    },
    summary: {
      pendingHint: 'Génération du résumé…',
      failedTitle: 'Échec de la génération du résumé',
      failedFallback: 'Erreur inconnue',
      empty: 'Aucune donnée de résumé',
      sections: {
        intent: 'Intent',
        keyQuestions: 'Key Questions',
        actionItems: 'Action Items',
        sentiment: 'Sentiment',
      },
      sentimentNeutral: 'neutral',
    },
    rel: {
      seconds: 'il y a {n} s',
      minutes: 'il y a {n} min',
      hours: 'il y a {n} h',
      days: 'il y a {n} j',
    },
    duration: '{m}m {s}s',
    errors: {
      load: 'Échec du chargement : {msg}',
      loadMore: 'Échec du chargement supplémentaire : {msg}',
      detail: 'Échec du chargement des détails : {msg}',
    },
  },
  debug: {
    intro: 'Flux brut d\'événements EventBroadcaster (1000 derniers). Non requis pour les démos courantes — conservé pour le diagnostic.',
    empty: 'Aucun événement pour l\'instant',
    rawMode: 'Mode brut',
  },
};
