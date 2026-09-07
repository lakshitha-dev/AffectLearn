export interface TokenResponse {
  accessToken: string;
  refreshToken: string;
  tokenType: string;
  expiresIn: number;
}

export interface UserResponse {
  id: string;
  emailAddress: string;
  firstName: string;
  lastName: string;
  role: "learner" | "course_designer" | "admin";
  // Collected at registration and editable from the profile form. The API has always returned
  // these; they were simply absent from this type because nothing rendered them.
  ageRange?: string | null;
  degreeProgram?: string | null;
  consentGivenAt?: string | null;
  webcamEnabled?: boolean;
}

export interface MessageResponse {
  message: string;
}

export interface ApiError {
  error: {
    code: string;
    message: string;
  };
}
