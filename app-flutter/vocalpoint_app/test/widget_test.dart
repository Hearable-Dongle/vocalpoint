import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:vocalpoint_app/main.dart';

void main() {
  testWidgets('Home page renders navigation entry points',
      (WidgetTester tester) async {
    await tester.pumpWidget(const MyApp());

    expect(find.text('Home'), findsOneWidget);
    expect(find.text('Bluetooth Setup'), findsOneWidget);
    expect(find.text('Volume Control'), findsOneWidget);
  });

  testWidgets('Bluetooth setup page opens from Home',
      (WidgetTester tester) async {
    await tester.pumpWidget(const MyApp());
    await tester.tap(find.widgetWithText(ElevatedButton, 'Bluetooth Setup'));
    await tester.pumpAndSettle();

    expect(find.text('Scan for devices'), findsOneWidget);
    expect(find.text('Found devices'), findsOneWidget);
  });
}
