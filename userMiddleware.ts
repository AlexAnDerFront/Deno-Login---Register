import { Context } from "@oak/oak";
import { validate } from "@zaubrik/djwt";
import { users, User } from "./users.ts";

const userMiddleware = async (ctx: Context, next: Function) => {
  try {
    const jwt = ctx.cookies.get('jwt');
    if (jwt) {
      const jwtKey = Deno.env.get('JWT_KEY');
      if (!jwtKey) {
        console.error("JWT_KEY environment variable not set");
        ctx.state.currentUser = null;
      } else {
        // Await the validate operation
        const data = await validate(jwt, jwtKey);
        if (data) {
          const user = users.find((u: User) => u.username === data.payload.iss);
          ctx.state.currentUser = user || null;
        } else {
          ctx.cookies.delete('jwt');
          ctx.state.currentUser = null;
        }
      }
    } else {
      ctx.state.currentUser = null;
    }
  } catch (error) {
    console.error("Error validating JWT:", error);
    ctx.cookies.delete('jwt');
    ctx.state.currentUser = null;
  }
  
  await next();
};

export default userMiddleware;