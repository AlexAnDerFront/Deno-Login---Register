import { RouterContext } from "@oak/oak/router"; 
import {renderFileToString} from "@hongminhee/dejs";
import { hashSync, compareSync } from "@da/bcrypt";
import { users, User } from './users.ts';



export const home = async  (ctx: RouterContext) => {
    ctx.response.body = await renderFileToString(`${Deno.cwd()}/views/home.ejs`, {});
}
export const login = async  (ctx: RouterContext) => {
    ctx.response.body = await renderFileToString(`${Deno.cwd()}/views/login.ejs`, {});
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
    if (!user) {
        ctx.response.body = await renderFileToString(
        `${Deno.cwd()}/views/login.ejs`,
        { error: "Incorrect username"},
        );
    } else if (!compareSync(password, user.password)) {
        ctx.response.body = await renderFileToString(`${Deno.cwd()}/views/login.ejs`,
         {error: "Incorrect password"},
        );
    } else {
      console.log("Success"); 
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
