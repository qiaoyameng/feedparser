Added
-----

*   Add the immutable ``feedparser.sanitizer.SanitizationPolicy`` class and a
    new ``sanitization_policy`` parameter to ``feedparser.parse()``.

    A policy customizes the HTML sanitization whitelist -- allowed elements,
    attributes, URI schemes and CSS properties -- for a single parse call.
    Policies are never stored in global or class-level state, so concurrent
    calls, nested ``parse()`` calls and exceptions in one task cannot change
    the sanitization rules used by another task.

    ``SanitizationPolicy.default()`` reproduces the built-in sanitizer
    output exactly. ``SanitizationPolicy.restricted()`` only tightens the
    whitelist (unknown names raise ``ValueError``), while
    ``SanitizationPolicy.expanded()`` requires every additional allowed name
    to be declared explicitly and cannot implicitly widen another whitelist.

    The same policy applies to RSS/Atom HTML and XHTML content and to JSON
    Feed ``content_html``. Passing ``sanitize_html=False`` still disables
    sanitization entirely, regardless of the supplied policy.
