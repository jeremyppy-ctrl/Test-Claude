pluginManagement {
    repositories {
        google {
            content {
                includeGroupByRegex("com\\.android.*")
                includeGroupByRegex("com\\.google.*")
                includeGroupByRegex("androidx.*")
            }
        }
        mavenCentral()
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
    }
}

rootProject.name = "SlickChick"
include(":engine")

// The :app module needs the Android SDK. Keep the pure-Kotlin :engine module
// buildable and testable even on a machine that has no SDK installed.
val hasAndroidSdk = file("local.properties").takeIf { it.exists() }
    ?.let { f -> java.util.Properties().apply { f.inputStream().use(::load) }.getProperty("sdk.dir") != null }
    ?: (System.getenv("ANDROID_HOME") != null || System.getenv("ANDROID_SDK_ROOT") != null)

if (hasAndroidSdk) {
    include(":app")
} else {
    logger.lifecycle("No Android SDK found (local.properties/ANDROID_HOME) - skipping :app module.")
}
