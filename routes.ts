import { RouterContext } from "@oak/oak/router"; 
import { renderFileToString } from "@hongminhee/dejs";
import { hashSync, compareSync } from "@da/bcrypt";
import { create, Header, Payload } from "@zaubrik/djwt";
import { users, User } from "./users.ts";

const key = await crypto.subtle.generateKey(
    { name: "HMAC", hash: "SHA-256" },
    true,
    ["sign", "verify"],
  );
console.log(key);

try {
  await Deno.writeTextFile(".env", `JWT-Key:${key}`);
  console.log("Key written to .env file");
} catch (error) {
  console.error("Failed to write to .env file:", error);
}

const header: Header = {
    alg: 'HS256',
    typ: 'JWT'
  };

export const home = async  (ctx: RouterContext) => {
    ctx.response.body = await renderFileToString(`${Deno.cwd()}/views/home.ejs`, {});
}
export const login = async  (ctx: RouterContext) => {
    ctx.response.body = await renderFileToString(`${Deno.cwd()}/views/login.ejs`, { error: false, });
}
export const register = async  (ctx: RouterContext) => {
    ctx.response.body = await renderFileToString(`${Deno.cwd()}/views/register.ejs`, {});
}
export const protectedRoute = async  (ctx: RouterContext) => {
    ctx.response.body = await renderFileToString(`${Deno.cwd()}/views/protectedRoute.ejs`, {});
}
export const postLogin = async (ctx: RouterContext) => {
    const body = await ctx.request.body;
    const formData = await body.form();
    const username = formData.get("username");
    const password = formData.get("password");

    const user = users.find((u: User) => u.username === username);

    const wait = (t = 1000) => new Promise(r => setTimeout(r, t)); // OWAS Requirement für schutz von Timebased Attacks

    if (!user) {
        ctx.response.body = await renderFileToString(
        `${Deno.cwd()}/views/login.ejs`,
        { error: "Incorrect username"},
        );

        await wait();
    } else if (!compareSync(password, user.password)) {
        ctx.response.body = await renderFileToString(`${Deno.cwd()}/views/login.ejs`,
         {error: "Incorrect password"},
        );
        await wait();
    } else {
      console.log("Success"); 
      const payload: Payload = {
        iss: user.name,
        exp: new Date().getTime() + 1200
      };
      const jwt = await create(header, payload, key);
      ctx.cookies.set('jwt', jwt)
      ctx.response.redirect('/protectedRoute');
    }  
}
export const postRegister = async (ctx: RouterContext) => {
    if (ctx.request.hasBody) {
      const body = await ctx.request.body;
      const formData = await body.form();
      
      const name = formData.get("name");
      const username = formData.get("username");
      const password = formData.get("password");

      const hashedPassword = hashSync(password);

      const user: User = {
          name,                                                                                                                                                               
          username,
          password: hashedPassword
          
        };
        users.push(user);
        ctx.response.redirect('/login')
        console.log(users);
    } else {
      ctx.response.status = 400;
      ctx.response.body = "No data submitted";
    }
  }
export const logout = async  (ctx: RouterContext) => {
    ctx.response.body = await renderFileToString(`${Deno.cwd()}/views/logout.ejs`, {});
}
