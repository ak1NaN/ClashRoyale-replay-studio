import Java from 'frida-java-bridge';

let offline = false;
let installed = false;

rpc.exports = {
  setOffline(active) {
    return new Promise((resolve, reject) => {
      Java.perform(() => {
        try {
          const dialogs = Java.use('com.supercell.titan.NativeDialogManager');
          if (!installed) {
            const show = dialogs.ShowDialog.overload(
              'java.lang.String', 'java.lang.String', 'java.lang.String',
              'java.lang.String', 'java.lang.String'
            );
            show.implementation = function (title, message, a, b, c) {
              const text = `${title || ''} ${message || ''}`;
              if (offline && /连接中断|连接错误|重新登录|connection lost|connection error|disconnected|log in again|server.*respond/i.test(text)) {
                return -1;
              }
              return show.call(this, title, message, a, b, c);
            };
            installed = true;
          }
          offline = Boolean(active);
          if (offline) dialogs.nativeDialogDismissAll();
          resolve(true);
        } catch (error) {
          reject(error);
        }
      });
    });
  }
};
