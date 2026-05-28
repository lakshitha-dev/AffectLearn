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
  consentGivenAt?: string | null;
  webcamEnabled?: boolean;
}

export interface ApiError {
  error: {
    code: string;
    message: string;
  };
}
