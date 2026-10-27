# Android build environment for the Home Deck app: JDK 17 + Android SDK (platform 35, build-tools 35) + Gradle 8.10.2.
FROM eclipse-temurin:17-jdk-jammy
ENV ANDROID_HOME=/opt/android-sdk GRADLE_USER_HOME=/cache/gradle
RUN apt-get update && apt-get install -y --no-install-recommends unzip curl && rm -rf /var/lib/apt/lists/*
RUN mkdir -p $ANDROID_HOME/cmdline-tools && cd /tmp \
 && curl -fsSLo tools.zip https://dl.google.com/android/repository/commandlinetools-linux-11076708_latest.zip \
 && unzip -q tools.zip && mv cmdline-tools $ANDROID_HOME/cmdline-tools/latest && rm tools.zip
RUN yes | $ANDROID_HOME/cmdline-tools/latest/bin/sdkmanager --licenses >/dev/null \
 && $ANDROID_HOME/cmdline-tools/latest/bin/sdkmanager "platforms;android-35" "build-tools;35.0.0" "platform-tools" >/dev/null
RUN cd /opt && curl -fsSLo g.zip https://services.gradle.org/distributions/gradle-8.10.2-bin.zip && unzip -q g.zip && rm g.zip
ENV PATH=/opt/gradle-8.10.2/bin:$PATH
WORKDIR /src
