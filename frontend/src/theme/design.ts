/**
 * Modern Design System
 * Glassmorphism + Gradient Theme for Voice Agent Platform
 */

export const designTokens = {
  // Color Palette
  colors: {
    // Primary Gradient
    primaryGradient: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
    primaryGradientHover: 'linear-gradient(135deg, #5568d3 0%, #6a3f91 100%)',

    // Accent Colors
    accent: {
      blue: '#4facfe',
      purple: '#a78bfa',
      green: '#10b981',
      yellow: '#fbbf24',
      red: '#ef4444',
      cyan: '#22d3ee',
    },

    // Dark Mode Backgrounds
    dark: {
      bg: '#0f0f23',           // Main background
      elevated: '#1a1a2e',     // Card background
      hover: '#16213e',        // Hover state
      border: '#2d3748',       // Borders
      text: 'rgba(255, 255, 255, 0.85)',
      textSecondary: 'rgba(255, 255, 255, 0.55)',
    },

    // Light Mode Backgrounds
    light: {
      bg: '#f8fafc',
      elevated: '#ffffff',
      hover: '#f1f5f9',
      border: '#e2e8f0',
      text: 'rgba(0, 0, 0, 0.85)',
      textSecondary: 'rgba(0, 0, 0, 0.55)',
    },

    // Status Colors
    status: {
      success: '#10b981',
      warning: '#f59e0b',
      error: '#ef4444',
      info: '#3b82f6',
    },
  },

  // Typography
  typography: {
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
    fontSize: {
      xs: '12px',
      sm: '14px',
      base: '16px',
      lg: '18px',
      xl: '20px',
      '2xl': '24px',
      '3xl': '30px',
      '4xl': '36px',
    },
    fontWeight: {
      normal: 400,
      medium: 500,
      semibold: 600,
      bold: 700,
    },
  },

  // Spacing
  spacing: {
    xs: '4px',
    sm: '8px',
    md: '16px',
    lg: '24px',
    xl: '32px',
    '2xl': '48px',
    '3xl': '64px',
  },

  // Border Radius
  borderRadius: {
    sm: '4px',
    md: '8px',
    lg: '12px',
    xl: '16px',
    '2xl': '24px',
    full: '9999px',
  },

  // Shadows
  shadows: {
    sm: '0 1px 2px 0 rgb(0 0 0 / 0.05)',
    base: '0 1px 3px 0 rgb(0 0 0 / 0.1), 0 1px 2px -1px rgb(0 0 0 / 0.1)',
    md: '0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1)',
    lg: '0 10px 15px -3px rgb(0 0 0 / 0.1), 0 4px 6px -4px rgb(0 0 0 / 0.1)',
    xl: '0 20px 25px -5px rgb(0 0 0 / 0.1), 0 8px 10px -6px rgb(0 0 0 / 0.1)',
    glow: '0 0 20px rgba(102, 126, 234, 0.4)',
    glowHover: '0 0 30px rgba(102, 126, 234, 0.6)',
  },

  // Glassmorphism
  glass: {
    background: 'rgba(255, 255, 255, 0.05)',
    backdropFilter: 'blur(12px) saturate(150%)',
    border: '1px solid rgba(255, 255, 255, 0.1)',
    borderHover: '1px solid rgba(255, 255, 255, 0.2)',
  },

  // Transitions
  transitions: {
    fast: '150ms cubic-bezier(0.4, 0, 0.2, 1)',
    base: '300ms cubic-bezier(0.4, 0, 0.2, 1)',
    slow: '500ms cubic-bezier(0.4, 0, 0.2, 1)',
  },

  // Z-Index
  zIndex: {
    dropdown: 1000,
    sticky: 1100,
    modal: 1200,
    popover: 1300,
    tooltip: 1400,
  },
};

// CSS-in-JS Helpers
export const glassCard = (isDark: boolean) => ({
  background: isDark
    ? 'rgba(26, 26, 46, 0.7)'
    : 'rgba(255, 255, 255, 0.7)',
  backdropFilter: 'blur(12px) saturate(150%)',
  border: isDark
    ? '1px solid rgba(255, 255, 255, 0.1)'
    : '1px solid rgba(0, 0, 0, 0.1)',
  borderRadius: designTokens.borderRadius.lg,
  transition: `all ${designTokens.transitions.base}`,
});

export const glassCardHover = (isDark: boolean) => ({
  ...glassCard(isDark),
  border: isDark
    ? '1px solid rgba(255, 255, 255, 0.2)'
    : '1px solid rgba(0, 0, 0, 0.15)',
  boxShadow: designTokens.shadows.lg,
  transform: 'translateY(-2px)',
});

export const gradientButton = {
  background: designTokens.colors.primaryGradient,
  border: 'none',
  color: '#fff',
  fontWeight: designTokens.typography.fontWeight.semibold,
  borderRadius: designTokens.borderRadius.md,
  padding: '10px 24px',
  cursor: 'pointer',
  transition: `all ${designTokens.transitions.base}`,
  boxShadow: designTokens.shadows.md,
  ':hover': {
    background: designTokens.colors.primaryGradientHover,
    boxShadow: designTokens.shadows.glow,
    transform: 'translateY(-1px)',
  },
  ':active': {
    transform: 'translateY(0)',
  },
};

export const gradientBorder = {
  position: 'relative' as const,
  '::before': {
    content: '""',
    position: 'absolute' as const,
    inset: 0,
    borderRadius: 'inherit',
    padding: '1px',
    background: designTokens.colors.primaryGradient,
    WebkitMask: 'linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0)',
    WebkitMaskComposite: 'xor',
    maskComposite: 'exclude',
  },
};

export const pulsingDot = {
  position: 'relative' as const,
  display: 'inline-block',
  width: '8px',
  height: '8px',
  borderRadius: '50%',
  backgroundColor: designTokens.colors.status.success,
  '::before': {
    content: '""',
    position: 'absolute' as const,
    inset: 0,
    borderRadius: '50%',
    backgroundColor: 'inherit',
    animation: 'pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite',
  },
  '@keyframes pulse': {
    '0%, 100%': {
      opacity: 1,
      transform: 'scale(1)',
    },
    '50%': {
      opacity: 0.3,
      transform: 'scale(1.5)',
    },
  },
};

export default designTokens;
