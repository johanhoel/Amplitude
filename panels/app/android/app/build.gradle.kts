plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

// versionCode / versionName come from build.sh (-Pvc=... -Pvn=...); the server's /app/version.json must match.
val vc = (project.findProperty("vc") as String?)?.toInt() ?: 1
val vn = (project.findProperty("vn") as String?) ?: "dev"

android {
    namespace = "app.homedeck"
    compileSdk = 35
    buildToolsVersion = "35.0.0"
    lint { checkReleaseBuilds = false }
    defaultConfig {
        applicationId = "app.homedeck"
        minSdk = 26
        targetSdk = 35
        versionCode = vc
        versionName = vn
        buildConfigField("String", "BASE_URL", "\"https://home.example.net:8126\"")
    }
    buildFeatures { buildConfig = true }
    signingConfigs {
        create("release") {
            storeFile = file(System.getenv("HD_KEYSTORE") ?: "/signing/homedeck.jks")
            storePassword = System.getenv("HD_KS_PASS")
            keyAlias = "homedeck"
            keyPassword = System.getenv("HD_KS_PASS")
        }
    }
    buildTypes {
        release {
            isMinifyEnabled = false
            signingConfig = signingConfigs.getByName("release")
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
}

dependencies {
    implementation("com.google.android.gms:play-services-code-scanner:16.1.0")
}
