import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:vocalpoint_app/main.dart';

void main() {
  testWidgets('Home page renders navigation entry points',
      (WidgetTester tester) async {
    await tester.pumpWidget(const MyApp());

    expect(find.text('VocalPoint'), findsOneWidget);
    expect(find.text('Listening Device'), findsOneWidget);
    expect(find.text('Volume'), findsOneWidget);
  });

  testWidgets('Listening device page opens from Home',
      (WidgetTester tester) async {
    await tester.pumpWidget(const MyApp());
    await tester.tap(find.byIcon(Icons.hearing));
    await tester.pumpAndSettle();

    expect(find.text('Connect to Listening Device'), findsOneWidget);
    expect(find.text('Scan for devices'), findsOneWidget);
    expect(find.text('Available devices'), findsOneWidget);
  });
}
