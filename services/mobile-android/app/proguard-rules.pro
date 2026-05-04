# Retrofit
-keepattributes Signature
-keepattributes *Annotation*
-keep class retrofit2.** { *; }
-dontwarn retrofit2.**

# OkHttp
-dontwarn okhttp3.**
-dontwarn okio.**

# Kotlinx Serialization
-keepattributes RuntimeVisibleAnnotations,AnnotationDefault
-keepclassmembers class kotlinx.serialization.** { *; }
-keep,includedescriptorclasses class com.hems.companion.**$$serializer { *; }
-keepclassmembers class com.hems.companion.** {
    *** Companion;
}
-keepclasseswithmembers class com.hems.companion.** {
    kotlinx.serialization.KSerializer serializer(...);
}

# Hilt (KSP handles most; safety net)
-keep class dagger.hilt.android.internal.** { *; }
