// Nachgebaute Testdatei fuer das AC-6-Test-Fixture-Profil "kotlin".
// Weist count an drei Stellen zu.
class WidgetTest {
    fun testCountStartsAtOne() {
        val widget = Widget(count = 0)
        widget.count = 1
    }

    fun testCountStartsAtTwo() {
        val widget = Widget(count = 0)
        widget.count = 2
    }

    fun testCountStartsAtThree() {
        val widget = Widget(count = 0)
        widget.count = 3
    }
}
