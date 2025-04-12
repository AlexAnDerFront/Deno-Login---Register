import { Context } from "@oak/oak";
import { verify } from "@zaubrik/djwt"; // Also import verify
import { users, User } from "./users.ts";

const userMiddleware = async (ctx: Context, next: () => Promise<unknown>) => {
  // Get JWT from cookies
  const jwt = ctx.cookies.get('jwt');
  if (jwt) {
    try {
      // First, decode the JWT into its parts
      const jwtParts = (await jwt)?.split('.');
      const payload = JSON.parse(atob(jwtParts[1]));

      // Use verify instead of validate since you need to check the signature
      const jwtKey = Deno.env.get('JWT_KEY') || '';
      const secretKey = new TextEncoder().encode(jwtKey);
      
      // Use verify to check the signature
      const isValid = await verify(jwt, secretKey, { isThrowing: false });
      
      if (isValid) {
        // If it is valid select user and save in context state
        const user = users.find((u: User) => u.username === payload.iss);
        ctx.state.currentUser = user;
      } else {
        ctx.cookies.delete('jwt');
        ctx.state.currentUser = null;
      }
    } catch (error) {
      console.error("Error processing JWT:", error);
      ctx.cookies.delete('jwt');
      ctx.state.currentUser = null;
    }
  } else {
    ctx.state.currentUser = null;
  }
  await next();
}

export default userMiddleware ;