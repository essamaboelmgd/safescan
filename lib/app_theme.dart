import 'package:flutter/material.dart';

abstract final class MeyarColors {
  static const ink = Color(0xff143437);
  static const paper = Color(0xfff4f0e6);
  static const surface = Color(0xfffffdf8);
  static const terracotta = Color(0xffd77a54);
  static const sage = Color(0xff6f8b84);
  static const muted = Color(0xff63716c);
  static const line = Color(0xffe2ded3);
  static const warning = Color(0xff9a5e32);
  static const error = Color(0xffa53d32);
}

abstract final class MeyarTheme {
  static ThemeData get light {
    final scheme =
        ColorScheme.fromSeed(
          seedColor: MeyarColors.ink,
          brightness: Brightness.light,
        ).copyWith(
          primary: MeyarColors.ink,
          onPrimary: MeyarColors.paper,
          secondary: MeyarColors.terracotta,
          onSecondary: MeyarColors.ink,
          surface: MeyarColors.surface,
          onSurface: MeyarColors.ink,
          error: MeyarColors.error,
        );

    return ThemeData(
      useMaterial3: true,
      colorScheme: scheme,
      scaffoldBackgroundColor: MeyarColors.paper,
      appBarTheme: const AppBarTheme(
        backgroundColor: MeyarColors.paper,
        foregroundColor: MeyarColors.ink,
        elevation: 0,
        scrolledUnderElevation: 0,
        centerTitle: false,
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: MeyarColors.surface,
        contentPadding: const EdgeInsets.symmetric(
          horizontal: 16,
          vertical: 16,
        ),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(16),
          borderSide: const BorderSide(color: MeyarColors.line),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(16),
          borderSide: const BorderSide(color: MeyarColors.line),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(16),
          borderSide: const BorderSide(color: MeyarColors.ink, width: 1.5),
        ),
        errorBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(16),
          borderSide: const BorderSide(color: MeyarColors.error),
        ),
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          backgroundColor: MeyarColors.ink,
          foregroundColor: MeyarColors.paper,
          disabledBackgroundColor: MeyarColors.line,
          disabledForegroundColor: MeyarColors.muted,
          minimumSize: const Size(48, 52),
          padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 14),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(16),
          ),
          textStyle: const TextStyle(fontWeight: FontWeight.w700),
        ),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          foregroundColor: MeyarColors.ink,
          minimumSize: const Size(48, 50),
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 13),
          side: const BorderSide(color: MeyarColors.line),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(16),
          ),
          textStyle: const TextStyle(fontWeight: FontWeight.w600),
        ),
      ),
      navigationBarTheme: NavigationBarThemeData(
        backgroundColor: MeyarColors.surface,
        indicatorColor: MeyarColors.paper,
        elevation: 0,
        labelTextStyle: WidgetStateProperty.resolveWith((states) {
          final selected = states.contains(WidgetState.selected);
          return TextStyle(
            color: selected ? MeyarColors.ink : MeyarColors.muted,
            fontWeight: selected ? FontWeight.w700 : FontWeight.w500,
            fontSize: 12,
          );
        }),
      ),
      dividerColor: MeyarColors.line,
      textTheme: const TextTheme(
        headlineMedium: TextStyle(
          color: MeyarColors.ink,
          fontSize: 30,
          height: 1.12,
          fontWeight: FontWeight.w700,
          letterSpacing: -0.7,
        ),
        headlineSmall: TextStyle(
          color: MeyarColors.ink,
          fontSize: 25,
          height: 1.18,
          fontWeight: FontWeight.w700,
          letterSpacing: -0.4,
        ),
        titleLarge: TextStyle(
          color: MeyarColors.ink,
          fontSize: 20,
          fontWeight: FontWeight.w700,
        ),
        titleMedium: TextStyle(
          color: MeyarColors.ink,
          fontSize: 16,
          fontWeight: FontWeight.w700,
        ),
        bodyLarge: TextStyle(
          color: MeyarColors.ink,
          fontSize: 16,
          height: 1.45,
        ),
        bodyMedium: TextStyle(
          color: MeyarColors.ink,
          fontSize: 14,
          height: 1.45,
        ),
        bodySmall: TextStyle(
          color: MeyarColors.muted,
          fontSize: 12,
          height: 1.4,
        ),
        labelLarge: TextStyle(fontSize: 14, fontWeight: FontWeight.w700),
      ),
    );
  }
}
