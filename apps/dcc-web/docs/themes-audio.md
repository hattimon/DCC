# Themes and audio

Five complete variable sets style backgrounds, rail, surfaces, tables, headings, forms, dialogs, charts, status, buttons and store: Obsidian Graphite, Midnight Violet, Deep Ocean, Arctic Light and Emerald Terminal. They also differ in border contrast, corner radii and shadows. No theme downloads a third-party stylesheet or font.

Settings → Appearance previews changes immediately without a page reload. Save persists per user; cancel restores saved values; reset restores defaults. Accent, intensity, visual effects, density and animations are independent controls. `prefers-reduced-motion` disables motion even when the stored animation setting is enabled. Layout uses a responsive rail, four overview metrics, a container table with resource charts, and a phone navigation drawer.

Audio starts disabled. The user can enable it, adjust Master/effects/notifications levels, select Soft/Clear/Warm and test playback. Sounds start only after a browser gesture. Files are local short WAV assets copied from the project's existing authored audio packs; licensing/provenance is retained in `static/audio/LICENSES.md`. There is no music loop, autoplay intro or recurring sound timer.

Events include click, tab, start, stop, install, update, success, error, warning and notification. Browser autoplay policies can still block playback until the next interaction. The browser QA observes a real `playing` event for the test sound rather than checking only a stored preference.

The interface polls active data views at the user's interval (minimum 5 seconds, default 15), pauses while the tab is hidden or a form/dialog is active, and does not poll static store/settings views. Charts use recorded samples only; fewer than two measurements display an empty history. Monitoring history is bounded. Larger container tables scroll normally; there is no virtualized rendering in this version.
