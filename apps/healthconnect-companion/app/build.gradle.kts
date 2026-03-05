plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.hems.healthconnect"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.hems.healthconnect"
        minSdk = 34  // Health Connect background read requires Android 14+
        targetSdk = 35
        versionCode = 1
        versionName = "1.0.0"
    }

    buildTypes {
        release {
            isMinifyEnabled = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"))
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }

    buildFeatures {
        viewBinding = true
    }
}

dependencies {
    // Health Connect
    implementation("androidx.health.connect:connect-client:1.1.0-alpha10")

    // WorkManager for periodic background sync
    implementation("androidx.work:work-runtime-ktx:2.10.0")

    // HTTP client
    implementation("com.squareup.okhttp3:okhttp:4.12.0")

    // AndroidX
    implementation("androidx.core:core-ktx:1.15.0")
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("com.google.android.material:material:1.12.0")
    implementation("androidx.constraintlayout:constraintlayout:2.2.0")
    implementation("androidx.preference:preference-ktx:1.2.1")

    // JSON
    implementation("org.json:json:20240303")
}
