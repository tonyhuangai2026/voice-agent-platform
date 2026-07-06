// Voice Bot design tokens + naive-ui themeOverrides.
// AWS Console / Cloudscape-inspired enterprise palette.
//
// (Formerly kept byte-identical with the demo SPA's copy; the demo SPA was
// removed in the single-page merge — this is now the sole copy.)
//
// Two-track design system:
//   - naive-ui components consume `themeOverrides` (below) via <n-config-provider>.
//   - self-drawn components (BrandLogo / StatChip / MetricCard / EmptyState,
//     charts, waveform) consume CSS vars in styles/tokens.css (--vb-*), whose
//     dark values live under `html.dark`. The exported JS consts here mirror the
//     light-mode CSS values for any JS-side use (e.g. canvas drawing fallbacks).

// ---------------------------------------------------------------------------
// Raw palette
// ---------------------------------------------------------------------------
export const palette = {
  // Brand / primary (AWS Console blue — replaces legacy #0084FF)
  primary: '#0972D3',
  primaryHover: '#0B5FAE',
  primaryPressed: '#033160',
  primarySuppl: '#0B5FAE',

  // Ink + neutral grey scale (AWS squid ink at top)
  ink: '#232F3E',
  grey900: '#16191F',
  grey700: '#414D5C',
  grey500: '#687078',
  grey300: '#D5DBDB',
  grey200: '#EAEDED',
  grey100: '#FAFAFA',
  white: '#FFFFFF',

  // Accent (AWS orange — emphasis only, used sparingly)
  accent: '#FF9900',

  // Semantic
  success: '#037F0C',
  warning: '#FF9900',
  error: '#D91515',
  info: '#0972D3',
};

// ---------------------------------------------------------------------------
// JS token consts (for self-drawn components / canvas / SVG fallbacks).
// These mirror the LIGHT-mode values in tokens.css :root. Components that must
// follow dark mode should prefer the CSS vars (--vb-*); use these only where a
// JS value is unavoidable.
// ---------------------------------------------------------------------------
export const tokens = {
  color: {
    primary: palette.primary,
    primaryHover: palette.primaryHover,
    primaryPressed: palette.primaryPressed,
    accent: palette.accent,
    ink: palette.ink,
    success: palette.success,
    warning: palette.warning,
    error: palette.error,
    info: palette.info,

    // Surfaces (light)
    bg: palette.grey100,
    surface: palette.white,
    surfaceAlt: palette.grey200,
    border: palette.grey300,

    // Text (light)
    text: palette.ink,
    textSecondary: palette.grey700,
    textTertiary: palette.grey500,
    textInverse: palette.white,
  },
  radius: {
    sm: '4px',
    md: '8px',
    lg: '12px',
  },
  // 4px spacing grid
  space: {
    xs: '4px',
    sm: '8px',
    md: '12px',
    lg: '16px',
    xl: '24px',
    xxl: '32px',
  },
  shadow: {
    // 3-tier, low-saturation, Cloudscape-ish
    card: '0 1px 2px rgba(35,47,62,0.08), 0 1px 1px rgba(35,47,62,0.04)',
    popover: '0 4px 12px rgba(35,47,62,0.12), 0 2px 4px rgba(35,47,62,0.06)',
    modal: '0 12px 32px rgba(35,47,62,0.18), 0 4px 8px rgba(35,47,62,0.08)',
  },
  font: {
    family:
      "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'PingFang SC', 'Microsoft YaHei', system-ui, sans-serif",
    mono: "'SFMono-Regular', ui-monospace, 'Cascadia Code', Menlo, Consolas, monospace",
  },
};

// ---------------------------------------------------------------------------
// Dark-mode surface + text palette. Mirrors the `html.dark` block in
// styles/tokens.css so naive components and self-drawn (--vb-*) components stay
// visually aligned in dark mode. (BLOCKER-1 fix: themeOverrides is applied on
// top of BOTH naive base themes, so surface/text/border colours MUST be split
// per mode — otherwise naive cards/tables/inputs render light-on-dark.)
// ---------------------------------------------------------------------------
export const darkPalette = {
  // Brand (lifted for contrast on dark surfaces — matches tokens.css html.dark)
  primary: '#539FE5',
  primaryHover: '#6BB0EC',
  primaryPressed: '#89BDEE',
  primarySuppl: '#6BB0EC',

  accent: '#FFAA33',

  // Inverted ink + dark neutral surfaces
  ink: '#FAFAFA',
  bg: '#161D26',
  surface: '#1F2A37',
  surfaceAlt: '#2A3744',
  border: '#414D5C',
  borderStrong: '#687078',

  // Text
  text: '#FAFAFA',
  textSecondary: '#D5DBDB',
  textTertiary: '#9BA7B0',

  // Semantic (brightened for dark backgrounds)
  success: '#29AD32',
  warning: '#FFAA33',
  error: '#EB6F6F',
  info: '#539FE5',
};

// Mode-agnostic overrides: brand/semantic accents that read well on either
// background plus radius / typography. Spread into both light + dark sets.
const baseOverrides = {
  Button: {
    borderRadiusTiny: tokens.radius.sm,
    borderRadiusSmall: tokens.radius.sm,
    borderRadiusMedium: tokens.radius.sm,
    borderRadiusLarge: tokens.radius.md,
    fontWeight: '500',
  },
  Card: {
    borderRadius: tokens.radius.md,
    paddingMedium: '20px 24px',
  },
  Input: {
    borderRadius: tokens.radius.sm,
  },
  Tag: {
    borderRadius: tokens.radius.sm,
  },
  Menu: {
    borderRadius: tokens.radius.sm,
    itemHeight: '40px',
  },
  DataTable: {
    borderRadius: tokens.radius.md,
    thFontWeight: '600',
  },
  Tabs: {
    tabFontWeightActive: '600',
  },
  Tooltip: {
    borderRadius: tokens.radius.sm,
  },
  Popover: {
    borderRadius: tokens.radius.md,
  },
  Dialog: {
    borderRadius: tokens.radius.lg,
  },
};

// ---------------------------------------------------------------------------
// naive-ui themeOverrides — LIGHT. Bound in each App.vue via
// <n-config-provider :theme-overrides="darkMode ? darkThemeOverrides : themeOverrides">.
// ---------------------------------------------------------------------------
export const themeOverrides = {
  common: {
    // Brand
    primaryColor: palette.primary,
    primaryColorHover: palette.primaryHover,
    primaryColorPressed: palette.primaryPressed,
    primaryColorSuppl: palette.primarySuppl,

    // Semantic
    infoColor: palette.info,
    infoColorHover: palette.primaryHover,
    infoColorPressed: palette.primaryPressed,
    infoColorSuppl: palette.primaryHover,
    successColor: palette.success,
    successColorHover: '#0A8F14',
    successColorPressed: '#02690A',
    successColorSuppl: '#0A8F14',
    warningColor: palette.warning,
    warningColorHover: '#FFAA33',
    warningColorPressed: '#E68A00',
    warningColorSuppl: '#FFAA33',
    errorColor: palette.error,
    errorColorHover: '#E63535',
    errorColorPressed: '#B81212',
    errorColorSuppl: '#E63535',

    // Text
    textColorBase: palette.ink,
    textColor1: palette.ink,
    textColor2: palette.grey700,
    textColor3: palette.grey500,

    // Radius
    borderRadius: tokens.radius.sm,
    borderRadiusSmall: tokens.radius.sm,

    // Borders / dividers
    borderColor: palette.grey300,
    dividerColor: palette.grey200,

    // Surfaces
    bodyColor: palette.grey100,
    cardColor: palette.white,
    modalColor: palette.white,
    popoverColor: palette.white,
    tableColor: palette.white,
    inputColor: palette.white,
    actionColor: palette.grey100,

    // Shadows
    boxShadow1: tokens.shadow.card,
    boxShadow2: tokens.shadow.popover,
    boxShadow3: tokens.shadow.modal,

    // Typography
    fontFamily: tokens.font.family,
    fontFamilyMono: tokens.font.mono,
    fontWeightStrong: '600',
  },
  ...baseOverrides,
  Card: { ...baseOverrides.Card, color: palette.white },
  DataTable: {
    ...baseOverrides.DataTable,
    thColor: palette.grey200,
    thTextColor: palette.grey700,
  },
};

// ---------------------------------------------------------------------------
// naive-ui themeOverrides — DARK. Layered on top of naive's `darkTheme` base;
// keeps the AWS brand/semantic accents but uses dark surfaces + light text so
// cards / tables / inputs / popovers actually render dark.
// ---------------------------------------------------------------------------
export const darkThemeOverrides = {
  common: {
    // Brand (lifted)
    primaryColor: darkPalette.primary,
    primaryColorHover: darkPalette.primaryHover,
    primaryColorPressed: darkPalette.primaryPressed,
    primaryColorSuppl: darkPalette.primarySuppl,

    // Semantic
    infoColor: darkPalette.info,
    infoColorHover: darkPalette.primaryHover,
    infoColorPressed: darkPalette.primaryPressed,
    infoColorSuppl: darkPalette.primaryHover,
    successColor: darkPalette.success,
    successColorHover: '#3DBF45',
    successColorPressed: '#1F9A27',
    successColorSuppl: '#3DBF45',
    warningColor: darkPalette.warning,
    warningColorHover: '#FFBB55',
    warningColorPressed: '#E68A00',
    warningColorSuppl: '#FFBB55',
    errorColor: darkPalette.error,
    errorColorHover: '#F08888',
    errorColorPressed: '#D45656',
    errorColorSuppl: '#F08888',

    // Text (light on dark)
    textColorBase: darkPalette.text,
    textColor1: darkPalette.text,
    textColor2: darkPalette.textSecondary,
    textColor3: darkPalette.textTertiary,

    // Radius
    borderRadius: tokens.radius.sm,
    borderRadiusSmall: tokens.radius.sm,

    // Borders / dividers
    borderColor: darkPalette.border,
    dividerColor: darkPalette.border,

    // Surfaces (dark)
    bodyColor: darkPalette.bg,
    cardColor: darkPalette.surface,
    modalColor: darkPalette.surface,
    popoverColor: darkPalette.surfaceAlt,
    tableColor: darkPalette.surface,
    inputColor: darkPalette.surfaceAlt,
    actionColor: darkPalette.surfaceAlt,

    // Shadows (deeper on dark)
    boxShadow1: '0 1px 2px rgba(0,0,0,0.40), 0 1px 1px rgba(0,0,0,0.24)',
    boxShadow2: '0 4px 12px rgba(0,0,0,0.48), 0 2px 4px rgba(0,0,0,0.32)',
    boxShadow3: '0 12px 32px rgba(0,0,0,0.56), 0 4px 8px rgba(0,0,0,0.40)',

    // Typography
    fontFamily: tokens.font.family,
    fontFamilyMono: tokens.font.mono,
    fontWeightStrong: '600',
  },
  ...baseOverrides,
  Card: { ...baseOverrides.Card, color: darkPalette.surface },
  DataTable: {
    ...baseOverrides.DataTable,
    thColor: darkPalette.surfaceAlt,
    thTextColor: darkPalette.textSecondary,
  },
};

export default themeOverrides;
