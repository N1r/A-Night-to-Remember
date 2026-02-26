// 这个脚本可以在浏览器 console 里面跑，用来暴力查找和点击那个顽固的原创确认
(function() {
    console.log("=== WeChat Channels Dialog Bypass script ===");
    const findText = (query) => {
        let el = Array.from(document.querySelectorAll("*")).find(e => e.innerText && e.innerText.includes(query) && e.children.length === 0);
        return el;
    };
    
    // 1. 尝试暴力勾选“我已阅读”
    let readCheck = document.querySelector('.weui-desktop-icon-checkbox');
    if (readCheck){
        console.log("找到 checkbox, 尝试原生点选:", readCheck);
        readCheck.click();
    } else {
        let textNode = findText("我已阅读");
        if(textNode) {
            console.log("找到我已阅读文本节点，尝试点击父节点", textNode);
            textNode.parentElement.click();
            textNode.click();
        }
    }

    setTimeout(() => {
        // 2. 尝试暴力点“声明原创”
        let confirmBtn = findText("声明原创");
        if(confirmBtn) {
            console.log("找到声明原创文本节点", confirmBtn);
            if(confirmBtn.tagName === 'BUTTON') {
                confirmBtn.click();
            } else {
                confirmBtn.parentElement.click();
                confirmBtn.click();
                
                // 更极端的：找到含有该字样的最近 button
                let btn = Array.from(document.querySelectorAll("button, .weui-desktop-btn")).find(e => e.innerText && e.innerText.includes("声明原创"));
                if(btn) btn.click();
            }
        } else {
             console.log("警告: 没找到声明原创四个字!");
        }
    }, 1000);
})();
