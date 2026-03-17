import 'package:flutter_test/flutter_test.dart';

import 'package:vocalpoint_app/main.dart';

void main() {
  testWidgets('setup flow is shown after splash', (WidgetTester tester) async {
    await tester.pumpWidget(const MyApp());
    await tester.pump(const Duration(milliseconds: 1700));
    await tester.pumpAndSettle();

    expect(find.text('Build your signal chain'), findsOneWidget);
    expect(find.text('Connect to VocalPoint'), findsOneWidget);
    expect(find.text('Connect to Output Device'), findsOneWidget);
  });

  testWidgets('connection controls expand inline', (WidgetTester tester) async {
    await tester.pumpWidget(const MyApp());
    await tester.pump(const Duration(milliseconds: 1700));
    await tester.pumpAndSettle();

    await tester.tap(find.text('Connect to VocalPoint'));
    await tester.pumpAndSettle();

    expect(find.text('Scan for VocalPoint devices'), findsOneWidget);
    expect(find.text('No device selected'), findsOneWidget);
    expect(
      find.text('No devices yet. Start a scan to populate this list.'),
      findsOneWidget,
    );
  });

  testWidgets('skip enters dashboard without connected devices', (
    WidgetTester tester,
  ) async {
    await tester.pumpWidget(const MyApp());
    await tester.pump(const Duration(milliseconds: 1700));
    await tester.pumpAndSettle();

    await tester.tap(find.text('Skip'));
    await tester.pumpAndSettle();

    expect(find.text('Welcome back'), findsOneWidget);
    expect(find.text('VocalPoint offline'), findsOneWidget);
    expect(find.text('Output missing'), findsOneWidget);
  });
}
