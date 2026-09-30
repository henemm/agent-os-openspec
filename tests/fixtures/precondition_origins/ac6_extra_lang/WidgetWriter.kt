// Nachgebauter Produktivcode fuer das AC-6-Test-Fixture-Profil "kotlin".
// Schreibt count genau zweimal.
class WidgetWriter {
    fun increment(widget: Widget) {
        widget.count = widget.count + 1
    }

    fun reset(widget: Widget) {
        widget.count = 0
    }
}
