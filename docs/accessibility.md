# Accessibility

Last checked: 7 November 2026.

Vuurtoren supports keyboard navigation, narrow screens, and light and dark themes.
Automated checks cover part of accessibility. Screen-reader and real-phone checks
are still pending, so this statement does not establish WCAG conformance.

## Using the interface

- Use Tab and Shift+Tab to move between controls. Use arrow keys within Plan tab groups.
- Press Enter or Space to activate a button. Escape closes an editor and returns focus
  to its opener. Deleting that opener returns focus to the main content.
- Charts have written summaries. Account and cash-flow tables become labelled cards
  on narrow screens.
- Language, theme, and display currency can be changed in Settings. The system theme
  is the default. Editors and the demo loading indicator respect the reduced-motion preference.

## Automated checks

The checks use the fictional example household, Playwright 1.64.1, and the installed
Chromium, Firefox, and WebKit browser builds on Linux. WebKit runs in the matching
Playwright container. These are browser-engine checks, not tests of Safari on an iPhone.

| Build | Browsers | Coverage |
| --- | --- | --- |
| Self-hosted | Chromium | axe scans of Today, three Plan lenses, Flows, Settings, and an account editor in light and dark themes; a Dutch Plan scan |
| Self-hosted | Chromium, Firefox, WebKit | Critical navigation and editing, Settings saves, keyboard focus, and narrow touch layouts |
| Browser demo | Chromium | axe scans of the start screen, six app surfaces, and an account editor in light and dark themes; a Dutch Plan scan |
| Browser demo | Firefox, WebKit | Keyboard start, loading status, focus into the app, and the seeded account view |

Desktop checks use a 1280 × 720 viewport. Narrow checks emulate touch at 320 × 800 and
375 × 800, with reduced motion enabled. They measure page and content overflow, reach
all four views, scroll the Plan lens strip, and open and close an account editor.
Keyboard checks cover the editor's focus trap, Escape, and focus after deleting an account.
English is the default test locale; the Dutch scans also check the page language.

The axe helper selects WCAG 2.0 A/AA, 2.1 AA, and 2.2 AA rule tags. A passing scan
means those automated rules found no violations in the rendered states checked.
It does not evaluate every accessibility requirement.

The persistent checks live in the [self-hosted tests](../frontend/e2e/),
[browser-demo tests](../frontend/e2e-pyodide/), and
[server configuration](../frontend/playwright.config.ts) and
[demo configuration](../frontend/playwright.pyodide.config.ts).

## Human checks still needed

As of 7 November 2026, the following checks remain unverified:

1. On a physical phone, switch between portrait and landscape. Edit dates and decimal
   amounts with the software keyboard open. Check that the editor's controls remain reachable.
2. With VoiceOver and Safari, or NVDA and Firefox, navigate all views and an editor.
   Check chart summaries, field errors, loading announcements, and focus after closing dialogs.
3. Check browser zoom at 200% and 400%, larger system text, and forced-colour modes.
   Confirm that text, focus indicators, and chart alternatives remain usable.

## Reporting a problem

[Open an accessibility issue](https://github.com/simonvanlierde/vuurtoren/issues/new?title=Accessibility%3A%20).
Include the view, the action, the expected result, and your browser, device, and assistive
technology. Reproduce it with the example household where possible.
