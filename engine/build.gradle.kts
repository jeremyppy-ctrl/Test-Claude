plugins {
    id("org.jetbrains.kotlin.jvm")
}

kotlin {
    compilerOptions {
        jvmTarget.set(org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17)
    }
}

java {
    sourceCompatibility = JavaVersion.VERSION_17
    targetCompatibility = JavaVersion.VERSION_17
}

dependencies {
    testImplementation(kotlin("test"))
}

tasks.test {
    useJUnitPlatform()
    testLogging { events("passed", "failed", "skipped") }
}

// Dumps the table layout to JSON so tools/preview.html can render exactly the
// same geometry and artwork the game uses. Kotlin stays the single source of truth.
tasks.register<JavaExec>("exportTable") {
    group = "pinball"
    description = "Export the Slick Chick table description to tools/out/slick_chick.json"
    mainClass.set("com.pinball.engine.export.ExportKt")
    classpath = sourceSets["main"].runtimeClasspath
    args = listOf(rootProject.file("tools/out/slick_chick.json").absolutePath)
}
