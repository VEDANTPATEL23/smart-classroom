#include <Servo.h>

Servo baseServo;
Servo pivotServo;
Servo elbowServo;
Servo endEffectorServo;

void setup() {
  Serial.begin(115200);

  baseServo.attach(6);
  pivotServo.attach(7);
  elbowServo.attach(8);
  endEffectorServo.attach(9);

  // Initial/default positions
  baseServo.write(90);
  pivotServo.write(145);
  elbowServo.write(145);
  endEffectorServo.write(118);
}

void loop() {

  // Python sends 4 angle values
  if (Serial.available() >= 4) {

    int baseAngle = Serial.read();
    int pivotAngle = Serial.read();
    int elbowAngle = Serial.read();
    int endAngle = Serial.read();

    // Extra safety limits
    baseAngle = constrain(baseAngle, 0, 180);
    pivotAngle = constrain(pivotAngle, 110, 180);
    elbowAngle = constrain(elbowAngle, 110, 180);
    endAngle = constrain(endAngle, 95, 140);

    baseServo.write(baseAngle);
    pivotServo.write(pivotAngle);
    elbowServo.write(elbowAngle);
    endEffectorServo.write(endAngle);
  }
} 
